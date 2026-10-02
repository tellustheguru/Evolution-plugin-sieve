"""GTK widgets for graphical editing of common Sieve filters."""

import re
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from sieve_filters import Action, Condition, Filter, render_filter


KINDS = {
    'from': 'Frånadress', 'to': 'Mottagaradress',
    'header': 'Rubrik', 'address': 'Adress', 'envelope': 'Kuvertadress',
    'exists': 'Rubrik finns', 'size': 'Storlek', 'body': 'Meddelandetext',
    'true': 'Alla meddelanden',
}


def _ui_kind(condition):
    if condition.kind in ('header', 'address') and condition.field.lower() == 'from':
        return 'from'
    if condition.kind in ('header', 'address') and condition.field.lower() == 'to':
        return 'to'
    return condition.kind


OPS = {'contains': 'innehåller', 'is': 'är', 'matches': 'matchar mönster',
       'over': 'större än', 'under': 'mindre än', 'exists': 'finns'}
ACTIONS = {
    'fileinto': 'Flytta till mapp', 'redirect': 'Vidarebefordra',
    'keep': 'Behåll', 'discard': 'Kassera', 'stop': 'Avsluta regler',
    'reject': 'Avvisa', 'ereject': 'Avvisa (utökat)',
    'addflag': 'Lägg till flagga', 'setflag': 'Sätt flagga', 'removeflag': 'Ta bort flagga',
    'vacation': 'Automatiskt svar',
}


def _combo(values, selected):
    widget = Gtk.ComboBoxText()
    for key, label in values.items():
        widget.append(key, label)
    widget.set_active_id(selected)
    return widget


def _row(grid, index, label, widget):
    caption = Gtk.Label(label=label)
    caption.set_xalign(0)
    grid.attach(caption, 0, index, 1, 1)
    widget.set_hexpand(True)
    grid.attach(widget, 1, index, 1, 1)


def _list_view(columns):
    store = Gtk.ListStore(*([str] * len(columns)))
    view = Gtk.TreeView(model=store)
    for index, label in enumerate(columns):
        view.append_column(Gtk.TreeViewColumn(label, Gtk.CellRendererText(), text=index))
    scroll = Gtk.ScrolledWindow()
    scroll.set_min_content_height(100)
    scroll.add(view)
    return store, view, scroll


def _selected_index(view):
    model, iterator = view.get_selection().get_selected()
    return model.get_path(iterator).get_indices()[0] if iterator else None


class FilterDialog(Gtk.Dialog):
    def __init__(self, parent, original=None):
        super().__init__(title='Redigera filter' if original else 'Nytt filter', transient_for=parent, flags=0)
        self.add_buttons('Avbryt', Gtk.ResponseType.CANCEL, 'Spara filter', Gtk.ResponseType.OK)
        self.set_default_size(780, 550)
        self.conditions = list(original.conditions) if original else []
        self.actions = list(original.actions) if original else []
        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        form = Gtk.Grid(column_spacing=8, row_spacing=8)
        box.pack_start(form, False, False, 0)
        self.name = Gtk.Entry()
        self.name.set_text(original.name if original else '')
        _row(form, 0, 'Namn', self.name)
        self.enabled = Gtk.CheckButton(label='Aktiverat filter')
        self.enabled.set_active(original.enabled if original else True)
        form.attach(self.enabled, 1, 1, 1, 1)
        self.join = _combo({'allof': 'Alla villkor', 'anyof': 'Något villkor'}, original.join if original else 'allof')
        _row(form, 2, 'Matchning', self.join)
        box.pack_start(Gtk.Label(label='Villkor'), False, False, 0)
        self.condition_store, self.condition_view, scroll = _list_view(('Typ', 'Fält', 'Jämförelse', 'Värde', 'Inte'))
        box.pack_start(scroll, True, True, 0)
        self._buttons(box, 'condition')
        box.pack_start(Gtk.Label(label='Åtgärder i ordning'), False, False, 0)
        self.action_store, self.action_view, scroll = _list_view(('Åtgärd', 'Mapp/adress/text', 'Behåll kopia'))
        box.pack_start(scroll, True, True, 0)
        self._buttons(box, 'action')
        self.refresh()
        self.show_all()

    def _buttons(self, box, kind):
        row = Gtk.Box(spacing=6)
        box.pack_start(row, False, False, 0)
        for label, action in (('Lägg till', 'add'), ('Ändra vald', 'edit'), ('Ta bort vald', 'remove'),
                              ('Upp', 'up'), ('Ned', 'down')):
            button = Gtk.Button(label=label)
            button.connect('clicked', self._act, kind, action)
            row.pack_start(button, False, False, 0)

    def refresh(self):
        self.condition_store.clear()
        for item in self.conditions:
            self.condition_store.append((KINDS[_ui_kind(item)], item.field, OPS.get(item.operator, ''), item.value,
                                         'Ja' if item.negate else 'Nej'))
        self.action_store.clear()
        for item in self.actions:
            self.action_store.append((ACTIONS[item.kind], item.target, 'Ja' if item.copy else 'Nej'))

    def _act(self, button, kind, action):
        values = self.conditions if kind == 'condition' else self.actions
        view = self.condition_view if kind == 'condition' else self.action_view
        index = _selected_index(view)
        if action == 'add':
            value = self._edit_condition(None) if kind == 'condition' else self._edit_action(None)
            if value:
                values.append(value)
        elif index is None:
            return
        elif action == 'edit':
            value = self._edit_condition(values[index]) if kind == 'condition' else self._edit_action(values[index])
            if value:
                values[index] = value
        elif action == 'remove':
            del values[index]
        elif action in ('up', 'down'):
            other = index + (-1 if action == 'up' else 1)
            if 0 <= other < len(values):
                values[index], values[other] = values[other], values[index]
        self.refresh()

    def _edit_condition(self, original):
        dialog = Gtk.Dialog(title='Villkor', transient_for=self, flags=0)
        dialog.add_buttons('Avbryt', Gtk.ResponseType.CANCEL, 'OK', Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(12)
        dialog.get_content_area().add(grid)
        kind = _combo(KINDS, _ui_kind(original) if original else 'from')
        field = Gtk.Entry()
        field.set_text(original.field if original else 'From')
        field.set_placeholder_text('Till exempel From, To eller Subject')
        op = _combo(OPS, original.operator if original else 'contains')
        value = Gtk.Entry()
        value.set_text(original.value if original else '')
        negate = Gtk.CheckButton(label='Villkoret ska inte stämma')
        negate.set_active(original.negate if original else False)
        for row, label, widget in ((0, 'Typ', kind), (1, 'Fält', field), (2, 'Jämförelse', op), (3, 'Värde', value)):
            _row(grid, row, label, widget)
        grid.attach(negate, 1, 4, 1, 1)
        def update_fields(*_):
            chosen = kind.get_active_id()
            field.set_sensitive(chosen in ('header', 'address', 'envelope', 'exists'))
            op.set_sensitive(chosen not in ('exists', 'true'))
            value.set_sensitive(chosen not in ('exists', 'true'))
            value.set_placeholder_text('Till exempel 10M' if chosen == 'size' else 'Text som ska matchas')
        kind.connect('changed', update_fields)
        update_fields()
        dialog.show_all()
        result = None
        if dialog.run() == Gtk.ResponseType.OK:
            chosen_kind = kind.get_active_id()
            chosen_op = op.get_active_id()
            if chosen_kind in ('from', 'to'):
                chosen_field = 'From' if chosen_kind == 'from' else 'To'
                chosen_kind = original.kind if original and _ui_kind(original) == kind.get_active_id() else 'address'
            else:
                chosen_field = field.get_text().strip()
            if chosen_kind == 'exists':
                chosen_op = 'exists'
            elif chosen_kind in ('header', 'address', 'envelope') and chosen_op not in ('contains', 'is', 'matches'):
                chosen_op = 'contains'
            elif chosen_kind == 'size' and chosen_op not in ('over', 'under'):
                chosen_op = 'over'
            elif chosen_kind in ('body', 'true') and chosen_op not in ('contains', 'is', 'matches'):
                chosen_op = 'contains'
            result = Condition(chosen_kind, chosen_field, chosen_op, value.get_text(), negate.get_active())
        dialog.destroy()
        return result

    def _edit_action(self, original):
        dialog = Gtk.Dialog(title='Åtgärd', transient_for=self, flags=0)
        dialog.add_buttons('Avbryt', Gtk.ResponseType.CANCEL, 'OK', Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(12)
        dialog.get_content_area().add(grid)
        kind = _combo(ACTIONS, original.kind if original else 'fileinto')
        target = Gtk.Entry()
        target.set_text(original.target if original else '')
        target.set_placeholder_text('Mapp, adress eller text beroende på åtgärd')
        copy = Gtk.CheckButton(label='Behåll en kopia (:copy)')
        copy.set_active(original.copy if original else False)
        _row(grid, 0, 'Åtgärd', kind)
        _row(grid, 1, 'Mapp/adress/text', target)
        grid.attach(copy, 1, 2, 1, 1)
        def update_action(*_):
            chosen = kind.get_active_id()
            target.set_sensitive(chosen not in ('keep', 'discard', 'stop'))
            copy.set_sensitive(chosen in ('fileinto', 'redirect'))
            target.set_placeholder_text('Svarstext' if chosen == 'vacation' else 'Mapp, adress eller text')
        kind.connect('changed', update_action)
        update_action()
        dialog.show_all()
        result = None
        if dialog.run() == Gtk.ResponseType.OK:
            chosen_kind = kind.get_active_id()
            result = Action(chosen_kind, target.get_text(), copy.get_active() if chosen_kind in ('fileinto', 'redirect') else False)
        dialog.destroy()
        return result

    def value(self, original=None):
        item = Filter(self.name.get_text().strip(), self.join.get_active_id(),
                      self.conditions[:], self.actions[:], self.enabled.get_active(),
                      original.original if original else '', True)
        render_filter(item)
        return item


class FilterPanel(Gtk.Box):
    def __init__(self, parent):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.parent_window = parent
        self.document = None
        self.rows = []
        self.store, self.view, scroll = _list_view(('Filter', 'Villkor', 'Åtgärder', 'Status'))
        self.pack_start(scroll, True, True, 0)
        self.buttons = []
        buttons = Gtk.Box(spacing=8)
        self.pack_start(buttons, False, False, 0)
        for label, handler in (('Nytt filter', self.add), ('Ändra valt filter', self.edit),
                               ('Ta bort valt filter', self.remove), ('Flytta upp', self.move_up),
                               ('Flytta ned', self.move_down)):
            button = Gtk.Button(label=label)
            button.connect('clicked', handler)
            button.set_sensitive(False)
            self.buttons.append(button)
            buttons.pack_start(button, False, False, 0)

    def set_document(self, document):
        self.document = document
        for button in self.buttons:
            button.set_sensitive(document is not None and not document.opaque)
        self.refresh()

    def refresh(self):
        self.store.clear()
        self.rows = []
        if self.document is None:
            return
        if self.document.opaque:
            self.rows.append(None)
            self.store.append(('Skript med flerradig text', '–', '–', 'Kan inte redigeras grafiskt'))
            return
        for part in self.document.parts:
            if isinstance(part, Filter):
                self.rows.append(part)
                self.store.append((part.name or '(utan namn)', str(len(part.conditions)), str(len(part.actions)),
                                   'Aktiv' if part.enabled else 'Avaktiverad'))
            else:
                for match in re.finditer(r'(?m)^(?:# rule:\[([^\]\r\n]*)\]\r?\n)?if\s+', part):
                    name = match.group(1) or '(avancerat filter)'
                    self.rows.append(None)
                    self.store.append((name, '–', '–', 'Kan inte redigeras grafiskt'))

    def _selected(self):
        index = _selected_index(self.view)
        if index is None or index >= len(self.rows):
            return None
        item = self.rows[index]
        if item is None:
            self._error('Det här filtret använder Sieve-funktioner som den grafiska editorn ännu inte stöder. Regeln har inte ändrats.')
        return item

    def _error(self, error):
        self.parent_window._error(error)

    def _run_validated(self, dialog, original=None):
        while dialog.run() == Gtk.ResponseType.OK:
            try:
                return dialog.value(original)
            except ValueError as error:
                self._error(error)
        return None

    def add(self, *_):
        if self.document is None or self.document.opaque:
            return
        dialog = FilterDialog(self.parent_window._dialog_parent())
        item = self._run_validated(dialog)
        dialog.destroy()
        if item is not None:
            if self.document.parts and isinstance(self.document.parts[-1], str):
                if self.document.parts[-1] and not self.document.parts[-1].endswith('\n'):
                    self.document.parts[-1] += '\r\n'
            self.document.parts.extend((item, '\r\n'))
            self.refresh()

    def edit(self, *_):
        item = self._selected()
        if item is None:
            return
        dialog = FilterDialog(self.parent_window._dialog_parent(), item)
        changed = self._run_validated(dialog, item)
        dialog.destroy()
        if changed is not None:
            item.name, item.join, item.conditions, item.actions = changed.name, changed.join, changed.conditions, changed.actions
            item.enabled, item.dirty = changed.enabled, True
            self.refresh()

    def remove(self, *_):
        item = self._selected()
        if item is not None:
            self.document.parts.remove(item)
            self.refresh()

    def move_up(self, *_):
        self._move(-1)

    def move_down(self, *_):
        self._move(1)

    def _move(self, direction):
        item = self._selected()
        if item is None:
            return
        filters = self.document.filters
        index = filters.index(item)
        other = index + direction
        if 0 <= other < len(filters):
            left = self.document.parts.index(item)
            right = self.document.parts.index(filters[other])
            self.document.parts[left], self.document.parts[right] = self.document.parts[right], self.document.parts[left]
            self.refresh()
