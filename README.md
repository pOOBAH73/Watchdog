# PS5-Pro-Wächter

Prüft alle 10 Minuten MediaMarkt, Saturn und PlayStation Direct und schickt eine
Push-Nachricht aufs Handy (optional zusätzlich per E-Mail), sobald die PS5 Pro
bestellbar oder vorbestellbar ist und höchstens 899,99 € kostet.
Läuft kostenlos über GitHub Actions, dein Rechner muss nicht an sein.

## Einrichtung (ca. 10 Minuten)

1. **ntfy-App** aufs Handy (iOS/Android, kostenlos). Dort „Thema abonnieren“ und
   einen schwer zu erratenden Namen wählen, z. B. `ps5pro-k7f2q9xz`.
   Wer den Namen kennt, kann mitlesen, also nichts Offensichtliches.
2. **GitHub-Repository** anlegen (öffentlich empfohlen: dann sind die Actions-Minuten
   unbegrenzt; dein Thema-Name bleibt trotzdem geheim, weil er als Secret hinterlegt wird).
   Bei einem privaten Repo reichen die Freiminuten nur für etwa alle 30 Minuten,
   dann in `watch.yml` `*/10` durch `*/30` ersetzen.
3. Dateien hochladen: `check.py`, `requirements.txt`, `README.md`.
   Den Workflow am sichersten über „Add file → Create new file“ anlegen, als Namen
   `.github/workflows/watch.yml` eintippen und den Inhalt hineinkopieren
   (Ordner mit Punkt am Anfang gehen beim Drag-and-drop manchmal verloren).
4. **Settings → Secrets and variables → Actions → New repository secret**
   - `NTFY_TOPIC` = dein Thema-Name aus Schritt 1
   - optional `NTFY_EMAIL` = deine Mailadresse (bekommst die Treffer dann zusätzlich per Mail)
5. **Actions → PS5 Pro Wächter → Run workflow**, Häkchen bei „Test-Benachrichtigung“.
   Nach ca. 1 Minute sollte die Test-Push ankommen. Im Log siehst du pro Shop den Status.

## Status im Log

| Status          | Bedeutung                                              |
|-----------------|--------------------------------------------------------|
| `unavailable`   | ausverkauft                                            |
| `too_expensive` | lieferbar, aber über 899,99 € (z. B. Marktplatzhändler) |
| `available`     | kaufbar → Push mit höchster Priorität                  |
| `blocked`       | Shop hat den Abruf abgewiesen (Bot-Schutz)             |
| `unknown`       | Seite geladen, aber keine Produktdaten erkannt         |

Bleibt ein Shop eine Stunde lang `blocked`/`unknown`, kommt eine leise Info-Push,
damit du weißt, dass er gerade nicht überwacht wird.

## Anpassen

- Preisgrenze: unter Settings → Variables eine Variable `MAX_PRICE` setzen (Standard 899.99).
- Weitere Shops: in `check.py` in der Liste `SHOPS` ergänzen
  (`kind: "mms"` funktioniert für alle Seiten mit schema.org-Produktdaten).

## Falls MediaMarkt/Saturn GitHub blockieren

Die Server von GitHub stehen in Rechenzentren, und genau die blocken Shops gern.
Dann das Skript stattdessen zu Hause laufen lassen (Windows-Aufgabenplanung
oder Raspberry Pi alle 10 Minuten):

```
pip install curl_cffi
set NTFY_TOPIC=dein-thema
python check.py
```

## Hinweis

GitHub pausiert geplante Workflows in öffentlichen Repos nach 60 Tagen ohne
Aktivität und schickt dir dann eine Mail. Einfach in „Actions“ wieder aktivieren.
