import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate('firebase-credentials.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

currencies = ['USD', 'EUR', 'TRY', 'SAR', 'JOD', 'XAU']
for cur in currencies:
    doc = db.collection('rates').document(cur).get()
    if doc.exists:
        data = doc.to_dict()
        sell = data.get('sell_price', 0)
        buy = data.get('buy_price', 0)
        source = data.get('source', '?')
        ts = data.get('timestamp', None)
        print(f"{cur}: sell={sell:,.0f}  buy={buy:,.0f}  source={source}  time={ts}")
    else:
        print(f"{cur}: NOT FOUND")
