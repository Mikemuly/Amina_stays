"""Default wording for every automated message. Amina can override any of them per language from the
console (messaging.Template). Keep SMS GSM-7 friendly: plain quotes, '-' not dashes, no emoji."""

DEFAULTS = {
    # ---------- account ----------
    "otp": {
        "en": "Your {business} code is {code}. It expires in 5 minutes. Never share it - we will never call to ask for it.",
        "sw": "Nambari yako ya {business} ni {code}. Itaisha baada ya dakika 5. Usimpe mtu yeyote.",
        "it": "Il tuo codice {business} e {code}. Scade tra 5 minuti. Non condividerlo con nessuno.",
        "de": "Dein {business}-Code ist {code}. Er läuft in 5 Minuten ab. Gib ihn niemals weiter.",
        "fr": "Votre code {business} est {code}. Il expire dans 5 minutes. Ne le partagez jamais.",
    },
    # ---------- booking & payment ----------
    "hold_mpesa": {
        "en": "Holding {unit} for {dates} ({nights} night{s}). Check your phone for an M-Pesa prompt of {amount}. Ref {ref}. Pay only via this official prompt - we never ask you to send money to a personal number.",
        "sw": "Tumekuwekea {unit} kwa {dates} (usiku {nights}). Angalia simu yako kwa ombi la M-Pesa la {amount}. Kumb. {ref}. Lipa tu kupitia ombi hili rasmi - hatutakuomba utume pesa kwa nambari ya mtu.",
        "it": "Teniamo {unit} per {dates} ({nights} notti). Controlla il telefono per la richiesta M-Pesa di {amount}. Rif. {ref}.",
        "de": "Wir halten {unit} für {dates} ({nights} Nächte). Bitte bestätige die M-Pesa-Anfrage über {amount} auf deinem Handy. Ref. {ref}.",
        "fr": "Nous gardons {unit} pour {dates} ({nights} nuits). Validez la demande M-Pesa de {amount} sur votre telephone. Ref {ref}.",
    },
    "hold_card": {
        "en": "Holding {unit} for {dates}. Pay {amount} securely by card within {minutes} min: {link} (ref {ref})",
        "sw": "Tumekuwekea {unit} kwa {dates}. Lipa {amount} kwa kadi ndani ya dakika {minutes}: {link} (kumb. {ref})",
        "it": "Teniamo {unit} per {dates}. Paga {amount} con carta entro {minutes} min: {link} (rif. {ref})",
        "de": "Wir halten {unit} für {dates}. Bezahle {amount} per Karte innerhalb von {minutes} Min.: {link} (Ref. {ref})",
        "fr": "Nous gardons {unit} pour {dates}. Payez {amount} par carte sous {minutes} min : {link} (ref {ref})",
    },
    "pay_link": {
        "en": "Hi {first_name}, please pay {amount} for {ref} ({unit}) securely by card: {link} - we never ask you to send money to a personal number.",
        "sw": "Habari {first_name}, tafadhali lipa {amount} kwa {ref} ({unit}) kwa kadi hapa: {link} - hatutakuomba utume pesa kwa nambari ya mtu.",
        "it": "Ciao {first_name}, paga {amount} per {ref} ({unit}) in modo sicuro con carta: {link}",
        "de": "Hallo {first_name}, bitte bezahle {amount} für {ref} ({unit}) sicher per Karte: {link}",
        "fr": "Bonjour {first_name}, merci de payer {amount} pour {ref} ({unit}) par carte en toute securite : {link}",
    },
    "payment_failed": {
        "en": "Your payment for {ref} didn't go through ({reason}). Reply PAY to try again - we hold {unit} a few more minutes.",
        "sw": "Malipo yako ya {ref} hayakufanikiwa ({reason}). Jibu PAY kujaribu tena - tunashikilia {unit} kwa dakika chache zaidi.",
        "it": "Il pagamento per {ref} non e andato a buon fine ({reason}). Rispondi PAY per riprovare.",
        "de": "Deine Zahlung für {ref} ist fehlgeschlagen ({reason}). Antworte PAY, um es erneut zu versuchen.",
        "fr": "Votre paiement pour {ref} a echoue ({reason}). Repondez PAY pour reessayer.",
    },
    "hold_expired": {
        "en": "We didn't receive payment in time, so {unit} for {dates} was released. Reply BOOK to try again.",
        "sw": "Hatukupokea malipo kwa wakati, kwa hivyo {unit} kwa {dates} imeachiliwa. Jibu BOOK kujaribu tena.",
    },
    "booking_confirmed": {
        "en": "Booked! {unit}, {dates} ({nights} night{s}). Ref {ref}. Paid {paid}.{balance_note} Your trip: {trip_link} - Reply HELP any time for urgent help.",
        "sw": "Imethibitishwa! {unit}, {dates} (usiku {nights}). Kumb. {ref}. Umelipa {paid}.{balance_note} Safari yako: {trip_link} - Jibu MSAADA wakati wowote kwa msaada wa dharura.",
        "it": "Prenotato! {unit}, {dates} ({nights} notti). Rif. {ref}. Pagato {paid}.{balance_note} Il tuo viaggio: {trip_link} - Rispondi HELP per aiuto urgente.",
        "de": "Gebucht! {unit}, {dates} ({nights} Nächte). Ref. {ref}. Bezahlt {paid}.{balance_note} Deine Reise: {trip_link} - Antworte HELP für dringende Hilfe.",
        "fr": "Reserve ! {unit}, {dates} ({nights} nuits). Ref {ref}. Paye {paid}.{balance_note} Votre sejour : {trip_link} - Repondez HELP pour une aide urgente.",
    },
    "balance_note": {
        "en": " Balance {balance} due {due_date}.",
        "sw": " Salio {balance} linadaiwa {due_date}.",
        "it": " Saldo {balance} entro {due_date}.",
        "de": " Restbetrag {balance} fällig am {due_date}.",
        "fr": " Solde {balance} du le {due_date}.",
    },
    "payment_received": {
        "en": "Payment received: {amount} for {ref}. {balance_line}",
        "sw": "Malipo yamepokelewa: {amount} kwa {ref}. {balance_line}",
    },
    "balance_due": {
        "en": "Hi {first_name}, the balance of {balance} for {ref} ({unit}) is due before arrival. {pay_prompt}: {trip_link}",
        "sw": "Habari {first_name}, salio la {balance} kwa {ref} ({unit}) linadaiwa kabla ya kufika. {pay_prompt}: {trip_link}",
    },
    "balance_reminder_soon": {
        "en": "Hi {first_name}, a quick heads-up: the balance of {balance} for {ref} ({unit}) is due on {due_date}. Pay any time by {pay_by}: {trip_link}",
        "sw": "Habari {first_name}, kumbusho: salio la {balance} kwa {ref} ({unit}) linadaiwa {due_date}. Lipa wakati wowote kwa {pay_by}: {trip_link}",
    },
    "balance_overdue": {
        "en": "Hi {first_name}, the balance of {balance} for {ref} ({unit}) was due on {due_date} and is still unpaid. Pay by {pay_by} on your trip page: {trip_link}{paybill_line} Your door code is sent once it's paid.",
        "sw": "Habari {first_name}, salio la {balance} kwa {ref} ({unit}) lilipaswa kulipwa {due_date} na bado halijalipwa. Lipa kwa {pay_by} kwenye ukurasa wa safari yako: {trip_link}{paybill_line} Nambari ya mlango itatumwa ukishalipa.",
    },
    "pay_prompt_failed": {
        "en": "We couldn't send the M-Pesa prompt for {ref} ({reason}). Reply PAY to try again, or pay by card here: {trip_link}",
        "sw": "Hatukuweza kutuma ombi la M-Pesa kwa {ref} ({reason}). Jibu PAY kujaribu tena, au lipa kwa kadi hapa: {trip_link}",
    },
    "late_payment_refund": {
        "en": "We received {amount} for {ref}, but {unit} was taken after your hold expired. Amina will refund you shortly. Sorry!",
        "sw": "Tumepokea {amount} kwa {ref}, lakini {unit} ilichukuliwa baada ya muda wako kuisha. Amina atakurudishia pesa hivi karibuni. Samahani!",
    },
    "refund_sent": {
        "en": "Refund sent: {amount} for {ref} to {destination}{reference_line}. Reply HELP if it hasn't reached you within a day.",
        "sw": "Marejesho yametumwa: {amount} kwa {ref} kwenda {destination}{reference_line}. Jibu MSAADA kama hayajakufikia ndani ya siku moja.",
    },
    "paybill_hint": {
        "en": "Or pay {amount} by M-Pesa Paybill {paybill}, account {ref}.",
        "sw": "Au lipa {amount} kwa M-Pesa Paybill {paybill}, akaunti {ref}.",
    },
    "payment_claim_matched": {
        "en": "Thank you - we found M-Pesa payment {code} for {amount} and added it to {ref}.",
        "sw": "Asante - tumepata malipo ya M-Pesa {code} ya {amount} na tumeyaongeza kwenye {ref}.",
    },
    "payment_claim_review": {
        "en": "Thanks - we've passed M-Pesa code {code} to {host}, who will match it to {ref} shortly. Please don't pay again.",
        "sw": "Asante - tumempa {host} nambari ya M-Pesa {code}, ataiunganisha na {ref} hivi karibuni. Tafadhali usilipe tena.",
    },
    # ---------- the guest message timeline ----------
    "pre_arrival": {
        "en": "Hi {first_name}! {unit} is ready for you on {check_in}. Help us prepare - reply: BREAKFAST to choose breakfast, ETA 3pm with your arrival time, or ARRIVE to tell us how you're travelling. Guide: {trip_link}",
        "sw": "Habari {first_name}! {unit} iko tayari kwako {check_in}. Tusaidie kujiandaa - jibu: BREAKFAST kuchagua kifungua kinywa, ETA 3pm saa utakayofika, au ARRIVE kutuambia unasafiri vipi. Mwongozo: {trip_link}",
        "it": "Ciao {first_name}! {unit} ti aspetta il {check_in}. Rispondi BREAKFAST per la colazione, ETA 15:00 con l'orario di arrivo, o ARRIVE per dirci come arrivi. Guida: {trip_link}",
        "de": "Hallo {first_name}! {unit} erwartet dich am {check_in}. Antworte BREAKFAST für Frühstück, ETA 15 Uhr mit deiner Ankunftszeit oder ARRIVE, wie du anreist. Guide: {trip_link}",
        "fr": "Bonjour {first_name} ! {unit} vous attend le {check_in}. Repondez BREAKFAST pour le petit-dejeuner, ETA 15h avec votre heure d'arrivee, ou ARRIVE pour votre moyen de transport. Guide : {trip_link}",
    },
    "id_request": {
        "en": "Kenyan tourism rules require a guest register. Please add your ID/passport before arrival: {trip_link} - or reply ID followed by the number. It is encrypted and used for nothing else.",
        "sw": "Sheria za utalii za Kenya zinahitaji rejista ya wageni. Tafadhali ongeza kitambulisho/pasipoti kabla ya kufika: {trip_link} - au jibu ID na nambari. Inahifadhiwa kwa usalama.",
        "it": "Le norme turistiche keniote richiedono un registro ospiti. Aggiungi il passaporto prima dell'arrivo: {trip_link} - o rispondi ID seguito dal numero.",
        "de": "Kenias Tourismusregeln verlangen ein Gästeregister. Bitte trage deinen Pass vor der Ankunft ein: {trip_link} - oder antworte ID gefolgt von der Nummer.",
        "fr": "La reglementation touristique kenyane exige un registre des clients. Ajoutez votre passeport avant l'arrivee : {trip_link} - ou repondez ID suivi du numero.",
    },
    "directions": {
        "en": "Karibu on {check_in}! {unit}: {directions} Landmark: {landmark}. Map: {map_link} Wi-Fi: {wifi}. Check-in from {checkin_time}. Your door code arrives by SMS on arrival day.",
        "sw": "Karibu {check_in}! {unit}: {directions} Alama: {landmark}. Ramani: {map_link} Wi-Fi: {wifi}. Kuingia kuanzia {checkin_time}. Nambari ya mlango itakuja kwa SMS siku ya kufika.",
        "it": "Benvenuto il {check_in}! {unit}: {directions} Punto di riferimento: {landmark}. Mappa: {map_link} Wi-Fi: {wifi}. Check-in dalle {checkin_time}. Il codice della porta arriva via SMS il giorno dell'arrivo.",
        "de": "Willkommen am {check_in}! {unit}: {directions} Orientierung: {landmark}. Karte: {map_link} WLAN: {wifi}. Check-in ab {checkin_time}. Den Türcode bekommst du am Anreisetag per SMS.",
        "fr": "Bienvenue le {check_in} ! {unit} : {directions} Repere : {landmark}. Carte : {map_link} Wi-Fi : {wifi}. Arrivee des {checkin_time}. Votre code de porte arrive par SMS le jour J.",
    },
    "checkin_code": {
        "en": "Welcome to {unit}! Door code: {code} (valid {valid_from} - {valid_until}). Wi-Fi: {wifi}. Reply CHECKOUT when you leave, or HELP for urgent help.",
        "sw": "Karibu {unit}! Nambari ya mlango: {code} (inatumika {valid_from} - {valid_until}). Wi-Fi: {wifi}. Jibu TOKA ukiondoka, au MSAADA kwa msaada wa dharura.",
        "it": "Benvenuto a {unit}! Codice porta: {code} (valido {valid_from} - {valid_until}). Wi-Fi: {wifi}. Rispondi CHECKOUT quando parti, o HELP per aiuto urgente.",
        "de": "Willkommen in {unit}! Türcode: {code} (gültig {valid_from} - {valid_until}). WLAN: {wifi}. Antworte CHECKOUT bei Abreise oder HELP für dringende Hilfe.",
        "fr": "Bienvenue a {unit} ! Code de porte : {code} (valable {valid_from} - {valid_until}). Wi-Fi : {wifi}. Repondez CHECKOUT au depart, ou HELP en cas d'urgence.",
    },
    "code_waiting_id": {
        "en": "Your door code for {unit} is ready, but we still need your ID/passport for the guest register: {trip_link} or reply ID followed by the number.",
        "sw": "Nambari yako ya mlango wa {unit} iko tayari, lakini bado tunahitaji kitambulisho/pasipoti: {trip_link} au jibu ID na nambari.",
        "it": "Il codice per {unit} e pronto, ma ci serve ancora il passaporto per il registro: {trip_link} o rispondi ID e numero.",
        "de": "Dein Türcode für {unit} ist bereit, aber wir brauchen noch deinen Pass für das Gästeregister: {trip_link} oder antworte ID und Nummer.",
        "fr": "Votre code pour {unit} est pret, mais il nous faut votre passeport pour le registre : {trip_link} ou repondez ID et numero.",
    },
    "code_waiting_balance": {
        "en": "Your door code for {unit} is ready once the balance of {balance} is paid. {reply_pay}: {trip_link}",
        "sw": "Nambari ya mlango wa {unit} itatumwa ukilipa salio la {balance}. {reply_pay}: {trip_link}",
    },
    "code_security_hold": {
        "en": "For your security we need to confirm your number before sending the door code for {unit}. Amina will call you shortly.",
        "sw": "Kwa usalama wako tunahitaji kuthibitisha nambari yako kabla ya kutuma nambari ya mlango wa {unit}. Amina atakupigia hivi karibuni.",
    },
    "local_tips": {
        "en": "Local tips for {area}: {tips} Taxi: {taxi}. Emergency: 999 or 112 (free), Red Cross 1199. Text HELP to reach Amina any time.",
        "sw": "Vidokezo vya {area}: {tips} Teksi: {taxi}. Dharura: 999 au 112 (bure), Red Cross 1199. Tuma MSAADA kumfikia Amina wakati wowote.",
        "it": "Consigli per {area}: {tips} Taxi: {taxi}. Emergenze: 999 o 112, Croce Rossa 1199. Scrivi HELP per contattare Amina.",
        "de": "Tipps für {area}: {tips} Taxi: {taxi}. Notruf: 999 oder 112, Rotes Kreuz 1199. Schreib HELP, um Amina jederzeit zu erreichen.",
        "fr": "Conseils pour {area} : {tips} Taxi : {taxi}. Urgences : 999 ou 112, Croix-Rouge 1199. Ecrivez HELP pour joindre Amina.",
    },
    "welcome_check": {
        "en": "Settled in at {unit}, {first_name}? Reply 1 if all is good, or just tell us what you need.",
        "sw": "Umetulia {unit}, {first_name}? Jibu 1 kama yote ni sawa, au tuambie unachohitaji.",
        "it": "Tutto bene a {unit}, {first_name}? Rispondi 1 se va tutto bene, o dicci di cosa hai bisogno.",
        "de": "Gut angekommen in {unit}, {first_name}? Antworte 1, wenn alles passt, oder sag uns, was du brauchst.",
        "fr": "Bien installe a {unit}, {first_name} ? Repondez 1 si tout va bien, ou dites-nous ce qu'il vous faut.",
    },
    "welcome_call_missed": {
        "en": "Karibu {first_name}! We called to welcome you to {unit} - sorry we missed you. Your door code is in our earlier SMS; directions and Wi-Fi are on your trip page: {trip_link} Reply here with any question, or HELP if it's urgent.",
        "sw": "Karibu {first_name}! Tulikupigia kukukaribisha {unit} - samahani hatukukupata. Nambari ya mlango iko kwenye SMS yetu ya awali; maelekezo na Wi-Fi yako hapa: {trip_link} Jibu hapa na swali lolote, au MSAADA kama ni dharura.",
    },
    "mid_stay": {
        "en": "Hope you're enjoying {area}! Fancy a mid-stay clean with fresh towels ({clean_price})? Reply CLEAN. Anything else, just reply.",
        "sw": "Tunatumaini unafurahia {area}! Ungependa usafi wa katikati ya kukaa na taulo mpya ({clean_price})? Jibu CLEAN.",
    },
    "checkout_reminder": {
        "en": "Checkout is tomorrow by {checkout_time}. Please leave keys inside, close windows and switch off the AC. Want more time? Reply LATE for late checkout or EXTEND to add a night.",
        "sw": "Kutoka ni kesho kabla ya {checkout_time}. Tafadhali acha funguo ndani, funga madirisha na zima AC. Unahitaji muda zaidi? Jibu LATE au EXTEND kuongeza usiku.",
        "it": "Il check-out e domani entro le {checkout_time}. Lascia le chiavi dentro, chiudi le finestre e spegni l'aria condizionata. Rispondi LATE per un check-out posticipato o EXTEND per una notte in piu.",
        "de": "Check-out ist morgen bis {checkout_time}. Bitte Schlüssel drinnen lassen, Fenster schließen, Klimaanlage aus. Antworte LATE für späten Check-out oder EXTEND für eine weitere Nacht.",
        "fr": "Le depart est demain avant {checkout_time}. Laissez les cles a l'interieur, fermez les fenetres et eteignez la clim. Repondez LATE pour un depart tardif ou EXTEND pour une nuit de plus.",
    },
    "checkout_thanks": {
        "en": "Thanks for staying with {business}! Your door code is now deactivated. Safe travels - karibu tena!",
        "sw": "Asante kwa kukaa na {business}! Nambari yako ya mlango imezimwa. Safari njema - karibu tena!",
        "it": "Grazie per aver soggiornato con {business}! Il codice della porta e ora disattivato. Buon viaggio!",
        "de": "Danke für deinen Aufenthalt bei {business}! Dein Türcode ist jetzt deaktiviert. Gute Reise!",
        "fr": "Merci d'avoir sejourne chez {business} ! Votre code est desactive. Bon voyage !",
    },
    "auto_checkout": {
        "en": "Checkout time has passed, so your door code for {ref} is now deactivated. Thank you and safe travels!",
        "sw": "Muda wa kutoka umepita, kwa hivyo nambari yako ya mlango ya {ref} imezimwa. Asante na safari njema!",
    },
    "review_request": {
        "en": "Asante for staying at {unit}! How was it? Reply 1 (poor) to 5 (excellent).",
        "sw": "Asante kwa kukaa {unit}! Ilikuwaje? Jibu 1 (mbaya) hadi 5 (bora kabisa).",
        "it": "Grazie per il soggiorno a {unit}! Com'e andata? Rispondi da 1 (male) a 5 (eccellente).",
        "de": "Danke für deinen Aufenthalt in {unit}! Wie war es? Antworte mit 1 (schlecht) bis 5 (ausgezeichnet).",
        "fr": "Merci pour votre sejour a {unit} ! Qu'en avez-vous pense ? Repondez de 1 (mauvais) a 5 (excellent).",
    },
    "review_comment": {
        "en": "Thank you! Anything you'd like to tell us or future guests? Reply with a comment, or SKIP.",
        "sw": "Asante! Kuna chochote ungependa kutuambia? Jibu na maoni, au SKIP.",
    },
    "review_thanks": {
        "en": "Asante sana for the {rating}/5! We'd love to host you again - just text us next time.",
        "sw": "Asante sana kwa {rating}/5! Tungependa kukukaribisha tena - tutumie ujumbe wakati ujao.",
    },
    "review_sorry": {
        "en": "We're sorry it wasn't great. Amina has been told personally and may reach out - reply with anything we should fix.",
        "sw": "Samahani haikuwa nzuri. Amina amearifiwa na anaweza kuwasiliana nawe - tuambie tunachopaswa kurekebisha.",
    },
    "rebook_offer": {
        "en": "Missing the coast, {first_name}? Book {unit} again direct for 10% off with code KARIBU10: {link} Reply STOP to opt out.",
        "sw": "Unaukumbuka ufuo, {first_name}? Weka nafasi {unit} tena moja kwa moja upate punguzo la 10% kwa KARIBU10: {link} Jibu STOP kujiondoa.",
    },
    "waitlist_offer": {
        "en": "Good news! {unit} ({price}/night) is free {dates}. Book it here: {link} - or reply BOOK. First to book gets it.",
        "sw": "Habari njema! {unit} ({price}/usiku) iko wazi {dates}. Weka nafasi hapa: {link} - au jibu BOOK. Wa kwanza kuweka anaipata.",
    },
    "waitlist_joined": {
        "en": "You're on the waitlist for {unit}, {dates}. We'll text you the moment it opens up.",
        "sw": "Uko kwenye orodha ya kusubiri ya {unit}, {dates}. Tutakutumia ujumbe mara tu itakapokuwa wazi.",
    },
    "change_requested": {
        "en": "{ref}: change to {new_dates} ({nights} night{s}, {guests} guest{gs}). New total {new_total} ({difference}). {next_step}",
        "sw": "{ref}: mabadiliko hadi {new_dates} (usiku {nights}, wageni {guests}). Jumla mpya {new_total} ({difference}). {next_step}",
    },
    "change_applied": {
        "en": "Done! {ref} at {unit} is now {dates} ({nights} night{s}, {guests} guest{gs}). New total {total}.{refund_line}{balance_note} {trip_link}",
        "sw": "Imekamilika! {ref} katika {unit} sasa ni {dates} (usiku {nights}, wageni {guests}). Jumla mpya {total}.{refund_line}{balance_note} {trip_link}",
    },
    "change_declined": {
        "en": "Sorry - we couldn't change {ref} to {new_dates}. Your booking stays as it was: {dates}.{refund_line}",
        "sw": "Samahani - hatukuweza kubadilisha {ref} hadi {new_dates}. Nafasi yako inabaki kama ilivyokuwa: {dates}.{refund_line}",
    },
    "cancelled_by_host": {
        "en": "We're very sorry - Amina has had to cancel {ref} ({unit}, {dates}).{refund_line}{goodwill_line}",
        "sw": "Samahani sana - Amina amelazimika kughairi {ref} ({unit}, {dates}).{refund_line}{goodwill_line}",
    },
    "cancelled_by_guest": {
        "en": "Your booking {ref} ({unit}, {dates}) is cancelled.{refund_line}",
        "sw": "Nafasi yako {ref} ({unit}, {dates}) imeghairiwa.{refund_line}",
    },
    "refund_line": {"en": " Refund of {amount} is on its way.", "sw": " Pesa {amount} zitarudishwa kwako."},
    "goodwill_line": {
        "en": " We've sent you KES {airtime} airtime as an apology.",
        "sw": " Tumekutumia salio la KES {airtime} kama pole.",
    },
    # ---------- Ask Amina (SMS bot) ----------
    "menu": {
        "en": "Ask Amina - reply with: PRICES, BOOK, BREAKFAST, WIFI, DIRECTIONS, STATUS, CHECKOUT, HELP (urgent) or STOP. Or just ask a question!",
        "sw": "Uliza Amina - jibu: BEI, BOOK, BREAKFAST, WIFI, MAELEKEZO, STATUS, TOKA, MSAADA (dharura) au STOP. Au uliza swali lolote!",
        "it": "Chiedi ad Amina - rispondi: PRICES, BOOK, BREAKFAST, WIFI, DIRECTIONS, STATUS, CHECKOUT, HELP (urgente). Oppure fai una domanda!",
        "de": "Frag Amina - antworte: PRICES, BOOK, BREAKFAST, WIFI, DIRECTIONS, STATUS, CHECKOUT, HELP (dringend). Oder stell einfach eine Frage!",
        "fr": "Demandez a Amina - repondez : PRICES, BOOK, BREAKFAST, WIFI, DIRECTIONS, STATUS, CHECKOUT, HELP (urgent). Ou posez votre question !",
    },
    "relay_ack": {
        "en": "Thanks! Amina will reply here shortly (usually within 15 minutes, 7am-10pm). For anything urgent reply HELP.",
        "sw": "Asante! Amina atakujibu hapa hivi karibuni (kwa kawaida ndani ya dakika 15, saa 1 asubuhi - 4 usiku). Kwa dharura jibu MSAADA.",
        "it": "Grazie! Amina ti rispondera qui a breve (di solito entro 15 minuti). Per urgenze rispondi HELP.",
        "de": "Danke! Amina antwortet dir hier in Kürze (meist innerhalb von 15 Minuten). Bei Dringendem antworte HELP.",
        "fr": "Merci ! Amina vous repondra ici rapidement (en general sous 15 minutes). En cas d'urgence, repondez HELP.",
    },
    "help_ack": {
        "en": "{call_line} She will contact you immediately. If you are in danger call 999 or 112 (police/ambulance) now.",
        "sw": "{call_line} Atawasiliana nawe mara moja. Ukiwa hatarini piga 999 au 112 (polisi/ambulensi) sasa.",
        "it": "{call_line} Ti contattera subito. Se sei in pericolo chiama ora il 999 o il 112.",
        "de": "{call_line} Sie meldet sich sofort. Bei Gefahr ruf jetzt 999 oder 112 an.",
        "fr": "{call_line} Elle vous contacte immediatement. En cas de danger appelez le 999 ou le 112.",
    },
    "help_calling": {
        "en": "We are calling Amina right now.",
        "sw": "Tunampigia Amina simu sasa hivi.",
        "it": "Stiamo chiamando Amina adesso.",
        "de": "Wir rufen Amina gerade an.",
        "fr": "Nous appelons Amina maintenant.",
    },
    "help_alerted": {
        "en": "Amina has been alerted urgently.",
        "sw": "Amina amearifiwa kwa dharura.",
        "it": "Amina e stata avvisata con urgenza.",
        "de": "Amina wurde dringend alarmiert.",
        "fr": "Amina a ete alertee en urgence.",
    },
    "opted_out": {
        "en": "You won't get promotional messages from {business} any more. Booking and safety messages will still reach you. Reply START to opt back in.",
        "sw": "Hutapokea tena ujumbe wa matangazo kutoka {business}. Ujumbe wa nafasi na usalama utaendelea. Jibu START kurudi.",
    },
    "opted_in": {
        "en": "You're subscribed to offers from {business}. Reply STOP any time.",
        "sw": "Umejiunga na ofa za {business}. Jibu STOP wakati wowote.",
    },
    "lang_set": {
        "en": "Language set to English.",
        "sw": "Lugha imewekwa: Kiswahili.",
        "it": "Lingua impostata: italiano.",
        "de": "Sprache eingestellt: Deutsch.",
        "fr": "Langue reglee : francais.",
    },
    "ask_dates": {
        "en": "{hello}Which dates? e.g. 'this weekend', 'tonight', '5 Dec for 3 nights' or '5-8 Dec'.",
        "sw": "{hello}Tarehe gani? mf. 'wikendi hii', 'leo usiku', '5 Des usiku 3' au '5-8 Des'.",
        "it": "{hello}Quali date? es. 'this weekend', 'tonight', '5 Dec for 3 nights'.",
        "de": "{hello}Welche Daten? z. B. 'this weekend', 'tonight', '5 Dec for 3 nights'.",
        "fr": "{hello}Quelles dates ? ex. 'this weekend', 'tonight', '5 Dec for 3 nights'.",
    },
    "options": {
        "en": "{hello}Yes! {dates}: {list}. Totals include fees. Reply {choices} to hold it.",
        "sw": "{hello}Ndiyo! {dates}: {list}. Bei zote ni jumla. Jibu {choices} kuishikilia.",
        "it": "{hello}Si! {dates}: {list}. Prezzi totali. Rispondi {choices} per bloccarla.",
        "de": "{hello}Ja! {dates}: {list}. Endpreise inkl. Gebühren. Antworte {choices}, um zu reservieren.",
        "fr": "{hello}Oui ! {dates} : {list}. Prix tout compris. Repondez {choices} pour reserver.",
    },
    "none_free": {
        "en": "Sorry, nothing is free for {dates}. We've added you to the waitlist and will text you if something opens up.",
        "sw": "Samahani, hakuna nafasi {dates}. Tumekuweka kwenye orodha ya kusubiri na tutakutumia ujumbe nafasi ikipatikana.",
        "it": "Spiacenti, nulla e libero per {dates}. Ti avviseremo se si libera qualcosa.",
        "de": "Leider ist für {dates} nichts frei. Wir melden uns, sobald etwas frei wird.",
        "fr": "Desole, rien n'est libre pour {dates}. Nous vous previendrons si une place se libere.",
    },
    "taken": {
        "en": "Sorry, someone just grabbed that one. Reply BOOK to see what's still free.",
        "sw": "Samahani, mtu ameichukua sasa hivi. Jibu BOOK kuona zilizobaki.",
    },
    "min_stay": {
        "en": "{unit} is free then, but has a minimum stay of {nights} nights. Reply with your dates for {nights} nights or more, e.g. '{example} for {nights} nights'.",
        "sw": "{unit} iko wazi, lakini inahitaji angalau usiku {nights}. Jibu na tarehe za usiku {nights} au zaidi, mf. '{example} usiku {nights}'.",
    },
    "price_list": {
        "en": "Our homes (per night, from): {list}. Reply BOOK with your dates to check availability.",
        "sw": "Nyumba zetu (kwa usiku, kuanzia): {list}. Jibu BOOK na tarehe zako kuangalia nafasi.",
    },
    "breakfast_menu": {
        "en": "Breakfast ({price}/person/day, served {time}): 1 Swahili (mahamri, chai, mbaazi, fruit) 2 Continental 3 Full English 4 Vegetarian/vegan. Reply a number, or 0 for none. Add HALAL/GLUTEN etc. if needed.",
        "sw": "Kifungua kinywa ({price}/mtu/siku, saa {time}): 1 Cha Kiswahili (mahamri, chai, mbaazi, matunda) 2 Continental 3 Kiingereza 4 Mboga/vegan. Jibu nambari, au 0 kama huhitaji.",
        "it": "Colazione ({price}/persona/giorno, ore {time}): 1 Swahili 2 Continentale 3 Inglese 4 Vegetariana/vegana. Rispondi con un numero, o 0 per nessuna.",
        "de": "Frühstück ({price}/Person/Tag, {time}): 1 Swahili 2 Kontinental 3 Englisch 4 Vegetarisch/vegan. Antworte mit einer Zahl, oder 0 für keins.",
        "fr": "Petit-dejeuner ({price}/pers./jour, {time}) : 1 Swahili 2 Continental 3 Anglais 4 Vegetarien/vegan. Repondez un chiffre, ou 0 pour aucun.",
    },
    "breakfast_saved": {
        "en": "Breakfast set: {summary}. The kitchen has been told. Change any time - reply BREAKFAST.",
        "sw": "Kifungua kinywa kimewekwa: {summary}. Jikoni wamearifiwa. Badilisha wakati wowote - jibu BREAKFAST.",
        "it": "Colazione impostata: {summary}. Rispondi BREAKFAST per cambiarla.",
        "de": "Frühstück gespeichert: {summary}. Ändern jederzeit mit BREAKFAST.",
        "fr": "Petit-dejeuner enregistre : {summary}. Repondez BREAKFAST pour modifier.",
    },
    "breakfast_none": {
        "en": "No problem - no breakfast for this stay. Reply BREAKFAST if you change your mind.",
        "sw": "Sawa - hakuna kifungua kinywa. Jibu BREAKFAST ukibadilisha mawazo.",
    },
    "eta_saved": {"en": "Thanks! We'll expect you around {eta}.", "sw": "Asante! Tutakutarajia karibu {eta}."},
    "arrival_question": {
        "en": "How are you getting here? 1 Flight (Moi Airport) 2 SGR train 3 Car/taxi 4 Bus 5 Already in Mombasa",
        "sw": "Unafikaje? 1 Ndege (Moi Airport) 2 Treni ya SGR 3 Gari/teksi 4 Basi 5 Tayari niko Mombasa",
    },
    "arrival_tips": {
        "en": "Thanks! {tip} Want a pickup? Reply PICKUP ({pickup_price}).",
        "sw": "Asante! {tip} Unahitaji kuchukuliwa? Jibu PICKUP ({pickup_price}).",
    },
    "request_sent": {
        "en": "We've asked Amina about {what}. You'll hear back shortly.",
        "sw": "Tumemuuliza Amina kuhusu {what}. Utajibiwa hivi karibuni.",
    },
    "request_approved": {
        "en": "Good news - {what} is confirmed for {unit}.{price_line}",
        "sw": "Habari njema - {what} imethibitishwa kwa {unit}.{price_line}",
    },
    "request_declined": {
        "en": "Sorry - {what} isn't possible this time (another guest arrives). Reply HELP if you need anything.",
        "sw": "Samahani - {what} haiwezekani wakati huu. Jibu MSAADA ukihitaji chochote.",
    },
    "issue_logged": {
        "en": "Sorry about that! Logged as #{task} - {assignee} has been notified and will sort it out. Reply HELP if it's an emergency.",
        "sw": "Samahani kwa hilo! Tumeandika #{task} - {assignee} amearifiwa na atashughulikia. Jibu MSAADA kama ni dharura.",
        "it": "Ci dispiace! Registrato come #{task} - {assignee} e stato avvisato. Rispondi HELP se e un'emergenza.",
        "de": "Das tut uns leid! Erfasst als #{task} - {assignee} ist informiert. Antworte HELP bei einem Notfall.",
        "fr": "Desole ! Enregistre sous #{task} - {assignee} est prevenu. Repondez HELP en cas d'urgence.",
    },
    "issue_fixed": {
        "en": "Update on #{task}: {title} has been fixed. Thanks for your patience!",
        "sw": "Taarifa ya #{task}: {title} imerekebishwa. Asante kwa uvumilivu!",
    },
    "id_saved": {
        "en": "Thank you - your {id_type} ending {last4} is registered.",
        "sw": "Asante - {id_type} yako inayoishia {last4} imesajiliwa.",
    },
    "no_booking": {
        "en": "We couldn't find an active booking for this number. Reply BOOK to make one.",
        "sw": "Hatukupata nafasi inayoendelea kwa nambari hii. Jibu BOOK kuweka nafasi.",
    },
    "cancel_quote": {
        "en": "Cancel {ref} ({unit}, {dates})? {refund_text} Reply YES to confirm or NO to keep it.",
        "sw": "Ghairi {ref} ({unit}, {dates})? {refund_text} Jibu NDIYO kuthibitisha au HAPANA kuiweka.",
    },
    "kept": {
        "en": "Great - {ref} is still on. See you soon!",
        "sw": "Vizuri - {ref} bado iko. Tutaonana hivi karibuni!",
    },
    "status": {
        "en": "{ref}: {unit}, {dates}. Status: {status}. Paid {paid} of {total}. {trip_link}",
        "sw": "{ref}: {unit}, {dates}. Hali: {status}. Umelipa {paid} kati ya {total}. {trip_link}",
    },
    "goodbye_ack": {"en": "Asante! Have a lovely stay.", "sw": "Asante! Kaa vizuri."},
    # ---------- staff & host ----------
    "staff_task": {
        "en": "New task #{id}: {title}{unit_line}, due {due}. Reply DONE {id} when finished, or START {id}.",
        "sw": "Kazi mpya #{id}: {title}{unit_line}, kabla ya {due}. Jibu DONE {id} ukimaliza.",
    },
    "kitchen_sheet": {"en": "Breakfasts for {date}: {lines}", "sw": "Kifungua kinywa {date}: {lines}"},
    "gate_list": {"en": "Gate list {date} (visitor log): {lines}", "sw": "Orodha ya geti {date}: {lines}"},
    "host_digest": {
        "en": "Good morning {host}! Today: {arrivals} arriving, {departures} leaving, {in_house} in-house, {breakfasts} breakfasts, {tasks} open tasks, {unread} chats waiting, {alerts} alerts. Week occupancy {occ}%.",
        "sw": "Habari za asubuhi {host}! Leo: {arrivals} wanafika, {departures} wanaondoka, {in_house} wako ndani, vifungua kinywa {breakfasts}, kazi {tasks}, ujumbe {unread}, tahadhari {alerts}.",
    },
    # ---------- support desk ----------
    "ticket_opened": {
        "en": 'We\'ve logged your request {ref}: "{subject}". {host} will get back to you within {sla}. Reply {ref} any time to check on it.',
        "sw": 'Tumepokea ombi lako {ref}: "{subject}". {host} atakujibu ndani ya {sla}. Jibu {ref} wakati wowote kujua hali yake.',
    },
    "ticket_callback": {
        "en": "Got it - {host} will call you back within {sla} (ref {ref}). If it's an emergency, reply HELP.",
        "sw": "Sawa - {host} atakupigia ndani ya {sla} (kumb. {ref}). Kama ni dharura, jibu MSAADA.",
    },
    "ticket_resolved": {
        "en": "Your request {ref} is resolved.{note}{rate_line}",
        "sw": "Ombi lako {ref} limeshughulikiwa.{note}{rate_line}",
    },
    "ticket_rate_line": {
        "en": "How did we do? Reply 1-5 (5 = excellent).",
        "sw": "Tulifanyaje? Jibu 1-5 (5 = bora kabisa).",
    },
    "ticket_thanks": {
        "en": "Thank you for rating us {rating}/5 - karibu tena!",
        "sw": "Asante kwa kutupa {rating}/5 - karibu tena!",
    },
    "ticket_sorry": {
        "en": "Thank you for telling us ({rating}/5). We're sorry - {host} will call you to put it right.",
        "sw": "Asante kwa kutueleza ({rating}/5). Samahani - {host} atakupigia kurekebisha.",
    },
    # ---------- service alerts ----------
    "notice_active": {
        "en": "Service alert at {unit}: {title}.{eta} {message}{data_line} Sorry for the trouble - we'll text you when it's fixed. Reply ALERTS for updates.",
        "sw": "Taarifa ya huduma {unit}: {title}.{eta} {message}{data_line} Samahani kwa usumbufu - tutakutumia ujumbe ikirekebishwa. Jibu ALERTS kwa taarifa mpya.",
    },
    "notice_heads_up": {
        "en": "Heads-up from {business}: {title} at {unit} on {when}.{eta} {message} Reply ALERTS for updates.",
        "sw": "Taarifa kutoka {business}: {title} {unit} tarehe {when}.{eta} {message} Jibu ALERTS kwa taarifa mpya.",
    },
    "notice_update": {
        "en": "Update - {title} at {unit}: {message}{eta}",
        "sw": "Taarifa mpya - {title} {unit}: {message}{eta}",
    },
    "notice_restored": {
        "en": "Good news: {title} at {unit} is over and everything is working again.{resolution} Asante for your patience!",
        "sw": "Habari njema: {title} {unit} imekwisha na kila kitu kinafanya kazi tena.{resolution} Asante kwa uvumilivu wako!",
    },
    "notice_cancelled": {
        "en": "Good news: the planned {title} at {unit} on {when} is cancelled - nothing changes for your stay.",
        "sw": "Habari njema: {title} iliyopangwa {unit} tarehe {when} imeahirishwa - hakuna kinachobadilika.",
    },
    "notice_known": {
        "en": "We know - {title} at {unit} since {since}.{eta} {message} No need to report it: we'll text you the moment it's fixed.",
        "sw": "Tunafahamu - {title} {unit} tangu {since}.{eta} {message} Hakuna haja ya kuripoti: tutakutumia ujumbe ikirekebishwa.",
    },
    "notice_eta": {"en": "Expected back by {time}.", "sw": "Inatarajiwa kurudi kufikia {time}."},
    "notice_data_line": {
        "en": "We've sent you {mb} MB of mobile data so you stay connected.",
        "sw": "Tumekutumia MB {mb} za data ili uendelee kuwa mtandaoni.",
    },
    "notice_data_sent": {
        "en": "Done - {mb} MB of mobile data is on its way to keep you connected until it's fixed.",
        "sw": "Tayari - MB {mb} za data zinakuja ili uendelee kuwa mtandaoni hadi irekebishwe.",
    },
    "notice_data_already": {
        "en": "You've already had your data bundle for this outage - we'll text you as soon as it's fixed.",
        "sw": "Tayari umepata data kwa tatizo hili - tutakutumia ujumbe likirekebishwa.",
    },
    "data_none": {
        "en": "The Wi-Fi at your home is working normally, so there's no outage data to send. You can swap points for data any time: reply POINTS.",
        "sw": "Wi-Fi ya nyumba yako inafanya kazi kama kawaida, kwa hivyo hakuna data ya tatizo. Unaweza kubadilisha pointi kuwa data: jibu POINTS.",
    },
    "notice_status": {"en": "Service status at {unit}: {list}", "sw": "Hali ya huduma {unit}: {list}"},
    "notice_all_clear": {
        "en": "All services are running normally at {unit}.",
        "sw": "Huduma zote zinafanya kazi kama kawaida {unit}.",
    },
    "notice_none": {
        "en": "No service alerts right now - everything is running normally.",
        "sw": "Hakuna taarifa za huduma kwa sasa - kila kitu kiko sawa.",
    },
    # ---------- rewards: airtime & data ----------
    "rewards_points": {
        "en": "Asante for staying with us! You earned {points} Amina Rewards points ({balance} in total). {redeem} points = KES {airtime} airtime or {data} MB of data. Reply POINTS any time.",
        "sw": "Asante kwa kukaa nasi! Umepata pointi {points} za Amina Rewards (jumla {balance}). Pointi {redeem} = salio la KES {airtime} au MB {data} za data. Jibu POINTS wakati wowote.",
    },
    "rewards_summary": {
        "en": "Amina Rewards: {balance} points.{redeem_line} Invite friends with code {code}: after their first stay you get KES {referrer} airtime and they get KES {referee}. Reply REFER to share it.",
        "sw": "Amina Rewards: pointi {balance}.{redeem_line} Alika marafiki kwa nambari {code}: baada ya safari yao ya kwanza utapata salio la KES {referrer} na wao KES {referee}. Jibu REFER kuishiriki.",
    },
    "rewards_can_redeem": {
        "en": "Reply REDEEM AIRTIME for KES {airtime} airtime or REDEEM DATA for {data} MB ({points} points each).",
        "sw": "Jibu REDEEM AIRTIME kwa salio la KES {airtime} au REDEEM DATA kwa MB {data} (pointi {points} kila moja).",
    },
    "rewards_progress": {
        "en": "{need} more points to your first reward.",
        "sw": "Pointi {need} zaidi hadi zawadi yako ya kwanza.",
    },
    "rewards_redeemed": {
        "en": "Done! {amount} is on its way to {phone}. You have {balance} points left.",
        "sw": "Tayari! {amount} inatumwa kwa {phone}. Umebaki na pointi {balance}.",
    },
    "rewards_redeem_sending": {
        "en": "Sending {amount} to {phone} now - we'll text you when it's done. You have {balance} points left.",
        "sw": "Tunatuma {amount} kwa {phone} sasa - tutakutumia ujumbe ikikamilika. Umebaki na pointi {balance}.",
    },
    "rewards_redeem_held": {
        "en": "Thanks! Your {amount} reward is waiting for {host}'s OK and will follow shortly. You have {balance} points left.",
        "sw": "Asante! Zawadi yako ya {amount} inasubiri idhini ya {host} na itafika hivi karibuni. Umebaki na pointi {balance}.",
    },
    "rewards_redeem_failed": {
        "en": "Sorry - we couldn't send your {amount} just now, so your points are back ({balance}). Please try again later.",
        "sw": "Samahani - hatukuweza kutuma {amount} sasa hivi, pointi zako zimerudishwa ({balance}). Tafadhali jaribu tena baadaye.",
    },
    "rewards_not_enough": {
        "en": "You have {balance} points - {need} more to redeem a reward. You earn points with every stay and for sharing feedback.",
        "sw": "Una pointi {balance} - unahitaji {need} zaidi kupata zawadi. Unapata pointi kila unapokaa nasi na ukitoa maoni.",
    },
    "rewards_not_kenyan": {
        "en": "Airtime and data rewards need a Kenyan (+254) number - your points stay saved for your next visit.",
        "sw": "Zawadi za salio na data zinahitaji nambari ya Kenya (+254) - pointi zako zimehifadhiwa.",
    },
    "rewards_data_off": {
        "en": "Data rewards aren't available right now - reply REDEEM AIRTIME to swap your points for airtime instead.",
        "sw": "Zawadi za data hazipatikani kwa sasa - jibu REDEEM AIRTIME kubadilisha pointi kuwa salio.",
    },
    "rewards_off": {
        "en": "Amina Rewards is paused at the moment - your points are safe.",
        "sw": "Amina Rewards imesimamishwa kwa sasa - pointi zako ziko salama.",
    },
    "rewards_refer": {
        "en": 'Share this: "Stay with {business} and get KES {amount} airtime after your first stay - text REF {code} to {number} before you book."',
        "sw": 'Shiriki hii: "Kaa na {business} upate salio la KES {amount} baada ya safari yako ya kwanza - tuma REF {code} kwa {number} kabla ya kuweka nafasi."',
    },
    "rewards_referral_ok": {
        "en": "Code {code} saved - thanks to {referrer}! After your first stay you'll both get airtime (KES {amount} for you).",
        "sw": "Nambari {code} imehifadhiwa - asante kwa {referrer}! Baada ya safari yako ya kwanza mtapata salio wote wawili (KES {amount} kwako).",
    },
    "rewards_referral_bad": {
        "en": "Sorry, that code didn't work: {reason}",
        "sw": "Samahani, nambari hiyo haikufanya kazi: {reason}",
    },
    "rewards_referrer_paid": {
        "en": "Your friend {friend} just finished their first stay with us - KES {amount} airtime is on its way to you. Asante for spreading the word!",
        "sw": "Rafiki yako {friend} amemaliza safari yake ya kwanza nasi - salio la KES {amount} linakuja kwako. Asante kwa kutuenezea!",
    },
    "rewards_referee_paid": {
        "en": "Karibu to Amina Rewards! As a guest a friend invited, KES {amount} airtime is on its way to you.",
        "sw": "Karibu Amina Rewards! Kama mgeni aliyealikwa na rafiki, salio la KES {amount} linakuja kwako.",
    },
    "rewards_gift": {
        "en": "{host} from {business} has sent you {amount}{why}. Asante!",
        "sw": "{host} wa {business} amekutumia {amount}{why}. Asante!",
    },
    # ---------- local guide ----------
    "guide_menu": {
        "en": "Explore the coast - reply with a number: {options}.",
        "sw": "Gundua pwani - jibu kwa nambari: {options}.",
    },
    "guide_list": {
        "en": "{title}: {list} Reply a number for hours, prices and a map.",
        "sw": "{title}: {list} Jibu nambari kupata saa, bei na ramani.",
    },
}

# Placeholder hints shown in the console template editor
PLACEHOLDERS = [
    "first_name",
    "name",
    "unit",
    "area",
    "ref",
    "dates",
    "check_in",
    "check_out",
    "nights",
    "total",
    "paid",
    "balance",
    "due_date",
    "checkin_time",
    "checkout_time",
    "wifi",
    "directions",
    "landmark",
    "map_link",
    "trip_link",
    "pay_by",
    "pay_prompt",
    "reply_pay",
    "business",
    "host",
    "tips",
    "taxi",
    "code",
    "valid_from",
    "valid_until",
    "points",
    "code",
    "amount",
    "title",
    "message",
    "eta",
]

DESCRIPTIONS = {
    "booking_confirmed": "Sent the moment payment succeeds",
    "pre_arrival": "3 days before arrival: breakfast, ETA and travel questions",
    "id_request": "Asks for the guest-register ID if it's missing",
    "balance_due": "Requests the balance for deposit bookings",
    "balance_reminder_soon": "A week before arrival: the balance and its due date (booked more than a week ahead)",
    "balance_overdue": "Balance still unpaid after its due date, before arrival",
    "pay_link": "Card payment link Amina sends from a reservation",
    "directions": "Day before arrival: directions, landmark, Wi-Fi",
    "checkin_code": "Arrival morning: the door code",
    "local_tips": "Arrival day: food, taxis, safety",
    "welcome_check": "Arrival evening: 'settled in?'",
    "mid_stay": "Day 2 of stays of 4+ nights",
    "checkout_reminder": "Evening before checkout",
    "checkout_thanks": "On checkout",
    "review_request": "After checkout (respecting quiet hours)",
    "rebook_offer": "3 weeks after checkout, opted-in direct guests only",
    "ticket_opened": "Support: a guest's request is logged, with its reference (T12)",
    "ticket_callback": "Support: a call-back request is logged",
    "ticket_resolved": "Support: the request is resolved (asks for a 1-5 rating when the guest isn't mid-conversation)",
    "notice_active": "Service alert: an outage starts (to guests staying, and arrivals before it's fixed)",
    "notice_heads_up": "Service alert: planned work, a day ahead",
    "notice_restored": "Service alert: it's over",
    "notice_known": "Reply when a guest reports a problem a service alert already covers",
    "rewards_points": "Rewards: points earned after a stay",
    "rewards_summary": "Rewards: the answer to POINTS",
    "rewards_referrer_paid": "Rewards: a friend the guest invited finished a first stay",
    "rewards_gift": "Airtime or data Amina sends herself",
}
