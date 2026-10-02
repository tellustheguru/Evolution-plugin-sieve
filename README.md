# Sieve-regler för Evolution 3.52

Grafisk redigerare för serverregler på Dovecot/Pigeonhole. I Evolutions e-postvy öppnas den via **Redigera → Serverfilter (Sieve)…** eller **Ctrl+Shift+S**. Redigeraren visas som en sida i Evolutions eget inställningsfönster och som **Serverfilter (Sieve)** i listan **Insticksmoduler**. Redigeraren använder ManageSieve på port 4190 med STARTTLS och verifierar servercertifikatet.

## Installera

För Ubuntu med Evolution 3.52, bygg och installera Debianpaketet:

```sh
sudo apt install evolution-dev libedataserver1.2-dev libgtk-3-dev python3-dev python3-gi pkg-config debhelper
./build-deb.sh
sudo apt install ./dist/evolution-sieve_0.1.0_amd64.deb
```

Paketet byggs för datorns arkitektur och lägger till filer under `/usr/lib/evolution/` och `/usr/share/evolution-sieve/`. Byggda `.deb`-filer hamnar i `dist/` och kan laddas upp som filer till en GitHub-release. På en dator där `./install.sh` redan har använts måste den gamla användarinstallationen tas bort före paketinstallationen, annars kan Evolution läsa in tillägget två gånger:

```sh
rm -f ~/.local/share/evolution/modules/lib/evolution/modules/module-evolution-sieve.so
rm -f ~/.local/share/evolution/modules/lib/evolution/plugins/org-gnome-evolution-sieve-editor.eplug
```

För en lokal installation utan paket går det fortfarande att använda:

```sh
sudo apt install evolution-dev libedataserver1.2-dev libgtk-3-dev python3-dev python3-gi gir1.2-gtk-3.0
./install.sh
```

Installationsskriptet frågar Evolutions bibliotek efter rätt användarkataloger för moduler och `.eplug`-beskrivningar. På Ubuntu med Evolution 3.52.3 ligger de under `~/.local/share/evolution/modules/lib/evolution/`.

Koden distribueras under GPL-3.0-or-later; se [LICENSE](LICENSE).

Starta om Evolution och öppna Sieve-sidan från menyn. Den hämtar automatiskt reglerna för det valda IMAP-kontot. Om du väljer menyalternativet igen visas samma inställningssida. **Hämta regler** uppdaterar dem manuellt vid behov. Redigeraren hämtar server och användarnamn från Evolution Data Server och försöker använda kontots sparade lösenord. ManageSieve använder port 4190 med STARTTLS. Om ManageSieve har en annan server eller inloggning öppnar **Anslutning…** en separat dialog. Serverinställningarna sparas per konto i `~/.config/evolution-sieve/config.ini`; lösenordet sparas inte av tillägget. Redigeraren kan också startas direkt med `python3 editor.py` för felsökning.

Kryssrutan i **Insticksmoduler** aktiverar eller inaktiverar Sieve-menyn och redigeraren. Om inställningssidan redan är öppen ligger den kvar i sidolistan tills Evolution startas om.

Om menyalternativet saknas, kör `./diagnose.sh` medan Evolutions huvudfönster är öppet. Skriptet visar om modulen har laddats i Evolution-processen.

## Regler

Efter anslutning listas serverns befintliga skript och det aktiva öppnas automatiskt. Välj ett befintligt filter i **Grafiska filter** och tryck **Ändra valt filter**. Där kan du redigera namn, aktivering, flera villkor och flera åtgärder. Du kan också lägga till, ta bort och flytta filter. **Spara skript** ändrar det valda skriptet; **Spara och aktivera** gör det aktivt.

Den grafiska vyn läser vanliga Sieve-filter oavsett vilket program som skapade dem; namngivna och namnlösa filter fungerar. Den stöder villkoren `header`, `address`, `envelope`, `exists`, `size`, `body` och `true`, samt åtgärderna `fileinto`, `redirect`, `keep`, `discard`, `stop`, `reject`, `ereject`, enkla `vacation` och IMAP-flaggor. Filter med annan Sieve-syntax visas som **Kan inte redigeras grafiskt** och lämnas orörda. Skript med `text:`-litteraler behandlas helt som råtext för att undvika feltolkning. En lokal säkerhetskopia sparas före ändring. Om skriptet ändrats på servern sedan det hämtades avbryts sparandet.

## Status och begränsningar

Parsern och regelgeneratorn har verifierats lokalt. Den inbäddade GTK-widgeten har provats i en isolerad C/GTK-process och modulen har länkats mot installerad Evolution 3.52.3. Sidan har visats i en körande Evolution-installation, men Debianpaketet har ännu inte installerats och provats där. Paketet passerar `lintian` och APT:s installationssimulering. Kör `python3 -m unittest -v` för regeltesterna.

Redigeraren stöder endast SASL PLAIN över STARTTLS. Den grafiska vyn täcker ännu inte all Sieve-syntax; fliken **Sieve-kod** kan öppna och redigera övrig syntax. Servern måste erbjuda ManageSieve och inloggning med lösenord. Om IMAP-kontot använder en annan autentiseringsmetod kan det sparade lösenordet inte nödvändigtvis användas mot ManageSieve.

Menyalternativet använder Evolution 3.52:s `GtkUIManager` och en `EExtension`. Redigeraren är en GTK-widget på en sida i `EPreferencesWindow` och körs inne i Evolution-processen. Python används för Sieve-logiken och den grafiska redigeraren.
Kontoläsning och ManageSieve-anrop körs i bakgrundstrådar så att Evolutions huvudfönster fortsätter svara medan servern arbetar.
