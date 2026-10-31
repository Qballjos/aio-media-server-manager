# TV Thuis koppelen

TV Thuis kan AIO gebruiken voor trends, recente media, afbeeldingen, zoeken, aanvragen en Verder kijken.
De tv hoeft geen AIO-beheerderswachtwoord, Jellyfin-adres of Jellyfin API-sleutel te bewaren.

1. Open op Android TV / Google TV **TV Thuis → Startscherm → AIO Media → Koppelen met AIO**.
2. Scan de QR-code met een telefoon op hetzelfde netwerk.
3. Open op die telefoon je bestaande AIO-installatie en ga naar **Instellingen → Account → Tv-koppelingen**.
4. Kies **Koppellink maken**, kopieer de link en plak hem op de telefoonpagina van de tv.
5. De tv controleert de link en bewaart de nieuwe koppeling. Gebruik **Verbinding testen** op de tv.

Een koppellink werkt één keer en verloopt na vijf minuten. Een nieuwe link maakt de vorige ongeldig.
Gebruik een AIO-adres dat vanaf de tv bereikbaar is: HTTPS of HTTP op het eigen netwerk. Het adres uit de link
wordt automatisch overgenomen. De tijdelijke telefoonpagina van TV Thuis gebruikt HTTP op het lokale netwerk.

Onder **Tv-koppelingen** kun je een afzonderlijke tv ontkoppelen; de verbinding werkt daarna niet meer.
**AIO ontkoppelen** op de tv trekt de eigen verbinding ook in. Andere tv's en de AIO-beheerderssessie blijven werken.
De tv kan media lezen en aanvragen, maar geen instellingen, processen, downloads of andere koppelingen beheren.
Verder kijken blijft, zoals bij de eerdere integratie, uit de Jellyfin-accounts van het huishouden verzameld.

## API-afspraak (versie 1)

| Route | Toegang | Functie |
| --- | --- | --- |
| `POST /api/tv/pairings` | Beheerder, bestaande CSRF-regels | Geeft `pairingCode`, `expiresIn: 300`. De dashboardlink bewaart de code in het URL-fragment. |
| `POST /api/tv/pairings/claim` | Eenmalige code, begrensd aantal pogingen | Body: `code`, `deviceName`. Antwoord: `version: 1`, `accessToken`, `deviceId`, `deviceName`. |
| `GET /api/tv/devices` | Beheerder | Namen, IDs en aanmaakmomenten; geen tokens. |
| `DELETE /api/tv/devices/{id}` | Beheerder | Trekt één tv-token in. |
| `POST /api/tv/disconnect` | Tv-token | Trekt alleen het eigen token in. |
| `GET /api/homepage/resume` | Tv-token of beheerder | Titel- en afleveringsvelden uit Jellyfin, zonder paden of credentials. |

Het tv-token is een apart, willekeurig bearer-token dat werkt tot het wordt ingetrokken. Serveropslag bevat alleen
hashes, in het privébestand `.tv-devices.json` in de configuratiemap. Dat bestand valt onder de bestaande
configuratieback-up; publiceer het niet. Er zijn geen nieuwe poorten of omgevingsvariabelen.

Verder kijken leest de al opgeslagen Jellyfin-sleutel op de server. Ontbreekt die, dan blijft de rij leeg;
het openen van de tv start geen installatie, sleutelontdekking of herstart van Jellyfin.
Oudere TV Thuis-versies blijven de bestaande handmatige integratie gebruiken.
