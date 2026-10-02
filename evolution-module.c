/* Evolution 3.52 extension: embed the graphical Sieve editor in Preferences. */
#include <Python.h>
#include <gtk/gtk.h>
#include <gmodule.h>
#include <libedataserver/libedataserver.h>

/* The public shell header includes every Evolution UI header.  We only need
 * this exported GType here, so keep the module independent of unrelated
 * address-book development headers. */
GType e_shell_window_get_type (void);
GtkUIManager *e_shell_window_get_ui_manager (gpointer shell_window);
const gchar *e_shell_window_get_active_view (gpointer shell_window);
gpointer e_shell_window_get_shell (gpointer shell_window);
GtkWidget *e_shell_get_preferences_window (gpointer shell);
typedef struct _EPreferencesWindow EPreferencesWindow;
typedef GtkWidget *(*EPreferencesWindowCreatePageFn) (EPreferencesWindow *window);
GType e_preferences_window_get_type (void);
void e_preferences_window_setup (EPreferencesWindow *window);
void e_preferences_window_add_page (EPreferencesWindow *window,
    const gchar *page_name, const gchar *icon_name, const gchar *caption,
    const gchar *help_target, EPreferencesWindowCreatePageFn create_fn,
    gint sort_order);
void e_preferences_window_show_page (EPreferencesWindow *window,
    const gchar *page_name);
#define E_TYPE_SHELL_WINDOW (e_shell_window_get_type ())

#ifndef SIEVE_EDITOR_PATH
#define SIEVE_EDITOR_PATH "editor.py"
#endif

typedef struct {
    EExtension parent;
    GtkUIManager *manager;
    GtkActionGroup *actions;
    GtkAction *open_action;
    guint merge_id;
} ESieveExtension;
typedef struct { EExtensionClass parent_class; } ESieveExtensionClass;

GType e_sieve_extension_get_type (void);
G_DEFINE_DYNAMIC_TYPE (ESieveExtension, e_sieve_extension, E_TYPE_EXTENSION)

static PyObject *python_page;
static EPreferencesWindow *registered_window;
static GtkWidget *sieve_page_widget;
static GSList *extensions;
static gboolean sieve_enabled = TRUE;
static gboolean sieve_enabled_loaded;

#define SIEVE_PLUGIN_ID "org.gnome.evolution.sieve-editor"

static gboolean
plugin_enabled (void)
{
    if (sieve_enabled_loaded)
        return sieve_enabled;
    GSettings *settings = g_settings_new ("org.gnome.evolution");
    gchar **disabled = g_settings_get_strv (settings, "disabled-eplugins");
    for (gchar **entry = disabled; *entry; entry++) {
        if (g_strcmp0 (*entry, SIEVE_PLUGIN_ID) == 0) {
            sieve_enabled = FALSE;
            break;
        }
    }
    g_strfreev (disabled);
    g_object_unref (settings);
    sieve_enabled_loaded = TRUE;
    return sieve_enabled;
}

static GtkWidget *
create_sieve_page (EPreferencesWindow *preferences)
{
    gchar *directory = g_path_get_dirname (SIEVE_EDITOR_PATH);
    PyObject *path, *directory_object, *module, *page_class, *capsule;
    GtkWidget *widget = NULL;
    PyGILState_STATE gil;
    (void) preferences;

    if (!Py_IsInitialized ()) {
        Py_Initialize ();
        PyEval_SaveThread ();
    }
    gil = PyGILState_Ensure ();
    Py_CLEAR (python_page);
    path = PySys_GetObject ("path");
    directory_object = PyUnicode_FromString (directory);
    if (path && directory_object)
        PyList_Insert (path, 0, directory_object);
    Py_XDECREF (directory_object);
    g_free (directory);

    module = PyImport_ImportModule ("editor");
    if (module) {
        page_class = PyObject_GetAttrString (module, "Editor");
        if (page_class) {
            python_page = PyObject_CallNoArgs (page_class);
            Py_DECREF (page_class);
        }
        Py_DECREF (module);
    }
    if (python_page) {
        capsule = PyObject_GetAttrString (python_page, "__gpointer__");
        if (capsule) {
            widget = PyCapsule_GetPointer (capsule, NULL);
            Py_DECREF (capsule);
        }
    }
    if (!widget || !GTK_IS_WIDGET (widget)) {
        if (PyErr_Occurred ())
            PyErr_Print ();
        g_warning ("Evolution Sieve: cannot create embedded editor");
        widget = gtk_label_new ("Sieve-redigeraren kunde inte startas. Se Evolutions logg.");
    }
    /* Preferences only shows the page widget; its children need to be shown here. */
    gtk_widget_show_all (widget);
    gtk_widget_set_sensitive (widget, plugin_enabled ());
    sieve_page_widget = widget;
    g_object_add_weak_pointer (G_OBJECT (widget), (gpointer *) &sieve_page_widget);
    PyGILState_Release (gil);
    return widget;
}

static EPreferencesWindow *
register_page (gpointer shell_window)
{
    if (!plugin_enabled ())
        return NULL;
    GtkWidget *widget = e_shell_get_preferences_window (e_shell_window_get_shell (shell_window));
    EPreferencesWindow *preferences;
    if (!widget || !G_TYPE_CHECK_INSTANCE_TYPE (widget, e_preferences_window_get_type ())) {
        g_warning ("Evolution Sieve: preferences window unavailable");
        return NULL;
    }
    preferences = (EPreferencesWindow *) widget;
    if (registered_window != preferences) {
        e_preferences_window_add_page (preferences, "sieve", "preferences-system",
            "Serverfilter (Sieve)", NULL, create_sieve_page, 450);
        registered_window = preferences;
        g_object_add_weak_pointer (G_OBJECT (preferences),
            (gpointer *) &registered_window);
    }
    return preferences;
}

static void
open_editor (gpointer shell_window)
{
    if (!plugin_enabled ())
        return;
    EPreferencesWindow *preferences = register_page (shell_window);
    if (!preferences)
        return;
    e_preferences_window_setup (preferences);
    gtk_window_set_transient_for (GTK_WINDOW (preferences), GTK_WINDOW (shell_window));
    e_preferences_window_show_page (preferences, "sieve");
    gtk_window_present (GTK_WINDOW (preferences));
}

static void
action_activated (GtkAction *action, gpointer data)
{
    ESieveExtension *self = data;
    (void) action;
    open_editor (e_extension_get_extensible (E_EXTENSION (self)));
}

static void
active_view_changed (GObject *object, GParamSpec *pspec, gpointer data)
{
    ESieveExtension *self = data;
    (void) pspec;
    if (self->open_action)
        gtk_action_set_visible (self->open_action,
            plugin_enabled () &&
            g_strcmp0 (e_shell_window_get_active_view (object), "mail") == 0);
}

static gboolean
key_pressed (GtkWidget *widget, GdkEventKey *event, gpointer data)
{
    (void) widget;
    ESieveExtension *self = data;
    if (plugin_enabled () &&
        g_strcmp0 (e_shell_window_get_active_view (widget), "mail") == 0 &&
        (event->state & (GDK_CONTROL_MASK | GDK_SHIFT_MASK)) ==
        (GDK_CONTROL_MASK | GDK_SHIFT_MASK) && event->keyval == GDK_KEY_S) {
        open_editor (e_extension_get_extensible (E_EXTENSION (self)));
        return TRUE;
    }
    return FALSE;
}

static void
install_menu_action (ESieveExtension *self)
{
    GtkWidget *window = GTK_WIDGET (e_extension_get_extensible (E_EXTENSION (self)));
    static const GtkActionEntry entries[] = {
        { "evolution-sieve-rules", NULL, "Serverfilter (Sieve)…", NULL,
          "Hantera e-postkontots Sieve-regler", G_CALLBACK (action_activated) }
    };
    if (self->manager)
        return;
    self->manager = e_shell_window_get_ui_manager (window);
    if (!self->manager)
        return;
    g_object_ref (self->manager);
    self->actions = gtk_action_group_new ("evolution-sieve");
    gtk_action_group_add_actions (self->actions, entries, G_N_ELEMENTS (entries), self);
    self->open_action = gtk_action_group_get_action (self->actions, "evolution-sieve-rules");
    gtk_ui_manager_insert_action_group (self->manager, self->actions, 0);
    self->merge_id = gtk_ui_manager_new_merge_id (self->manager);
    gtk_ui_manager_add_ui (self->manager, self->merge_id,
        "/main-menu/edit-menu/administrative-actions",
        "evolution-sieve-rules", "evolution-sieve-rules",
        GTK_UI_MANAGER_MENUITEM, FALSE);
    gtk_ui_manager_ensure_update (self->manager);
    active_view_changed (G_OBJECT (window), NULL, self);
}

static gboolean
window_mapped (GtkWidget *widget, GdkEventAny *event, gpointer data)
{
    (void) widget;
    (void) event;
    install_menu_action ((ESieveExtension *) data);
    return FALSE;
}

static void
e_sieve_extension_constructed (GObject *object)
{
    ESieveExtension *self = (ESieveExtension *) object;
    GtkWidget *window = GTK_WIDGET (e_extension_get_extensible (E_EXTENSION (object)));
    G_OBJECT_CLASS (e_sieve_extension_parent_class)->constructed (object);
    extensions = g_slist_prepend (extensions, self);
    g_signal_connect (window, "key-press-event", G_CALLBACK (key_pressed), self);
    g_signal_connect (window, "map-event", G_CALLBACK (window_mapped), self);
    g_signal_connect (window, "notify::active-view", G_CALLBACK (active_view_changed), self);
    register_page (window);
    install_menu_action (self);
    g_message ("Evolution Sieve: extension attached to shell window");
}

static void
e_sieve_extension_dispose (GObject *object)
{
    ESieveExtension *self = (ESieveExtension *) object;
    GtkWidget *window = GTK_WIDGET (e_extension_get_extensible (E_EXTENSION (object)));
    extensions = g_slist_remove (extensions, self);
    if (window)
        g_signal_handlers_disconnect_by_data (window, self);
    if (self->manager) {
        gtk_ui_manager_remove_ui (self->manager, self->merge_id);
        gtk_ui_manager_remove_action_group (self->manager, self->actions);
        g_clear_object (&self->actions);
        g_clear_object (&self->manager);
        self->open_action = NULL;
        self->merge_id = 0;
    }
    G_OBJECT_CLASS (e_sieve_extension_parent_class)->dispose (object);
}

static void
e_sieve_extension_class_init (ESieveExtensionClass *klass)
{
    GObjectClass *object_class = G_OBJECT_CLASS (klass);
    EExtensionClass *extension_class = E_EXTENSION_CLASS (klass);
    object_class->constructed = e_sieve_extension_constructed;
    object_class->dispose = e_sieve_extension_dispose;
    extension_class->extensible_type = E_TYPE_SHELL_WINDOW;
}

static void e_sieve_extension_class_finalize (ESieveExtensionClass *klass) { (void) klass; }
static void e_sieve_extension_init (ESieveExtension *self)
{
    self->manager = NULL;
    self->actions = NULL;
    self->open_action = NULL;
    self->merge_id = 0;
}

G_MODULE_EXPORT void e_module_load (GTypeModule *module)
{
    g_message ("Evolution Sieve: module loaded");
    e_sieve_extension_register_type (module);
}

G_MODULE_EXPORT void e_module_unload (GTypeModule *module) { (void) module; }

/* Called by Evolutions .eplug manager when the user toggles this entry. */
G_MODULE_EXPORT gint e_plugin_lib_enable (gpointer plugin, gint enabled)
{
    (void) plugin;
    sieve_enabled = enabled != 0;
    sieve_enabled_loaded = TRUE;
    if (sieve_page_widget)
        gtk_widget_set_sensitive (sieve_page_widget, sieve_enabled);
    for (GSList *link = extensions; link; link = link->next) {
        ESieveExtension *self = link->data;
        gpointer window = e_extension_get_extensible (E_EXTENSION (self));
        if (!window)
            continue;
        active_view_changed (G_OBJECT (window), NULL, self);
        if (enabled)
            register_page (window);
    }
    return 0;
}
