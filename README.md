# Wakeup

Eine kleine Windows-10/11-App, mit der ein Sender-PC einen Ziel-PC auffordert,
die Systemlautstaerke auf 100 % zu setzen und einen kurzen Ton abzuspielen.
Fuer Verbindungen ausserhalb des lokalen Netzwerks verbindet Tailscale beide
PCs ueber ein privates VPN.

## Zwei App-Versionen

Beide PCs muessen im selben Tailscale-Netzwerk (Tailnet) angemeldet sein.

- **Ziel-PC:** Zum Erstellen der EXE Python 3 mit Tkinter installieren und im
  Projektordner `build_receiver.bat` ausfuehren. Die fertige
  `dist\WakeupReceiver.exe` kann anschliessend auf dem Ziel-PC gestartet werden;
  dort ist keine Python-Installation erforderlich. Die EXE laeuft ohne
  Konsolenfenster. Nach erfolgreichem Start verschwindet das Fenster; das
  Wakeup-Symbol erscheint im Windows-Infobereich (gegebenenfalls unter den
  ausgeblendeten Symbolen).
  Ueber das Symbol laesst sich Wakeup wieder oeffnen oder beenden.
  **Mit Windows automatisch starten** ist standardmaessig aktiviert; der
  Empfaenger startet dann bei jeder Anmeldung dieses Windows-Benutzers. Lass
  die EXE dafuer an ihrem Speicherort, da der Autostart genau diesen Pfad nutzt.
  **Tailscale mit Windows starten** traegt zusaetzlich die Tailscale-App in
  denselben benutzerspezifischen Autostart ein.
  Die Tailscale-IP wird in der App angezeigt. Den angezeigten Kopplungscode
  einmal an den Sender weitergeben.
- **Sender-PC:** Python 3 mit Tkinter installieren, im Projektordner
  `python -m pip install -r requirements.txt` ausfuehren und dann
  `python sender.py` starten. Einmal die Tailscale-IP des Ziel-PCs, Port `8765`
  und Kopplungscode eingeben. Die Verbindung wird gespeichert. Danach genuegt
  der Knopf zum Senden; am Ziel-PC muss niemand Anfragen annehmen.

Der Kopplungscode und die Sender-Verbindung werden lokal im Benutzerprofil
gespeichert und muessen nur beim ersten Einrichten eingegeben werden. Die App
verwendet HTTP; ueber Tailscale wird die Verbindung zwischen den Geraeten durch
das VPN verschluesselt. Gib den Empfaenger-Port nicht per Router fuer das
oeffentliche Internet frei. Falls die Windows-Firewall nachfragt, erlaube den
Empfaenger fuer die Verbindung ueber Tailscale. Teile den Kopplungscode nur mit
deinem Sender-PC.

## Tests

`python -m unittest discover -s tests`