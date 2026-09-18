import os,secrets
from datetime import datetime,timezone
from flask import Flask,request,jsonify,render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc

app=Flask(__name__)
app.config.update(SECRET_KEY=os.getenv("SECRET_KEY",secrets.token_hex(32)),SQLALCHEMY_TRACK_MODIFICATIONS=False)
app.config["SQLALCHEMY_DATABASE_URI"]=os.getenv("DATABASE_URL","sqlite:///aquasentinel.db").replace("postgres://","postgresql://",1)
db=SQLAlchemy(app)

DEFAULTS={"temp_min":20.0,"temp_max":32.0,"ph_min":6.5,"ph_max":8.5,"turbidity_max":50.0}

class Reading(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 temperature=db.Column(db.Float,nullable=False)
 ph=db.Column(db.Float,nullable=False)
 turbidity=db.Column(db.Float,nullable=False)
 created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),index=True)

class Setting(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 key=db.Column(db.String(80),unique=True,nullable=False)
 value=db.Column(db.Float,nullable=False)

class Alert(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 sensor=db.Column(db.String(30),nullable=False)
 value=db.Column(db.Float,nullable=False)
 level=db.Column(db.String(20),nullable=False)
 message=db.Column(db.String(255),nullable=False)
 created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),index=True)

def device_ok():
 key=os.getenv("DEVICE_API_KEY","")
 return bool(key) and secrets.compare_digest(request.headers.get("X-Device-Key",""),key)

def cfg():
 d=DEFAULTS.copy()
 for x in Setting.query.all(): d[x.key]=x.value
 return d

def iso(dt):
 return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).isoformat()

def rd(x):
 return {"id":x.id,"temperature":x.temperature,"ph":x.ph,"turbidity":x.turbidity,"created_at":iso(x.created_at)}

def sensor_state(value,minimum,maximum):
 if value<minimum or value>maximum: return "CRITICAL"
 span=max(maximum-minimum,0.001)
 margin=span*0.10
 if value<=minimum+margin or value>=maximum-margin: return "WARNING"
 return "NORMAL"

def analyze(r,c):
 items=[
  ("Temperature",r.temperature,c["temp_min"],c["temp_max"],"°C"),
  ("pH",r.ph,c["ph_min"],c["ph_max"],""),
  ("Turbidity",r.turbidity,0,c["turbidity_max"]," NTU")
 ]
 results=[]
 for name,value,minimum,maximum,unit in items:
  state=sensor_state(value,minimum,maximum)
  if state=="CRITICAL":
   reason=f"{name} is outside the configured safe range ({minimum:g}–{maximum:g}{unit})"
  elif state=="WARNING":
   reason=f"{name} is approaching the configured limit ({minimum:g}–{maximum:g}{unit})"
  else:
   reason=f"{name} is within the configured range"
  results.append({"sensor":name,"value":value,"status":state,"message":reason})
 states=[x["status"] for x in results]
 overall="CRITICAL" if "CRITICAL" in states else ("WARNING" if "WARNING" in states else "NORMAL")
 return {"overall":overall,"sensors":results,"analyzed_at":iso(r.created_at)}

def evaluate(r,c):
 out=[]
 analysis=analyze(r,c)
 for x in analysis["sensors"]:
  if x["status"]=="CRITICAL":
   out.append((x["sensor"].lower(),x["value"],"CRITICAL",x["message"]))
 return out

@app.get("/health")
def health(): return jsonify(status="ok",service="AquaSentinel")

@app.get("/")
def dashboard(): return render_template("dashboard.html")

@app.get("/api/readings")
def api_readings():
 try: limit=max(1,min(int(request.args.get("limit",100)),1000))
 except: limit=100
 rows=Reading.query.order_by(desc(Reading.created_at)).limit(limit).all()
 return jsonify([rd(x) for x in rows[::-1]])

@app.get("/api/readings/latest")
def latest():
 x=Reading.query.order_by(desc(Reading.created_at)).first()
 return jsonify({"reading":rd(x) if x else None,"settings":cfg(),"analysis":analyze(x,cfg()) if x else {"overall":"NO DATA","sensors":[]}})

@app.get("/api/analysis")
def api_analysis():
 x=Reading.query.order_by(desc(Reading.created_at)).first()
 if not x: return jsonify({"overall":"NO DATA","message":"Waiting for the first ESP32 reading.","reading":None,"online":False,"sensors":[]})
 age=(datetime.now(timezone.utc)-x.created_at.replace(tzinfo=timezone.utc)).total_seconds()
 online=age<=30
 result=analyze(x,cfg())
 result.update({"reading":rd(x),"online":online,"age_seconds":round(age,1)})
 if not online:
  result["overall"]="OFFLINE"
  result["message"]="No ESP32 reading received in the last 30 seconds."
 else:
  result["message"]="Automatic analysis is running from the latest ESP32 sensor reading."
 return jsonify(result)

@app.get("/api/alerts")
def api_alerts():
 return jsonify([{"id":x.id,"sensor":x.sensor,"value":x.value,"level":x.level,"message":x.message,"created_at":iso(x.created_at)} for x in Alert.query.order_by(desc(Alert.created_at)).limit(100).all()])

@app.get("/api/settings")
def api_settings(): return jsonify(cfg())

@app.post("/api/settings")
def save_settings():
 data=request.get_json(silent=True) or {}
 for k in DEFAULTS:
  if k in data:
   try: v=float(data[k])
   except: continue
   x=Setting.query.filter_by(key=k).first() or Setting(key=k)
   x.value=v
   db.session.add(x)
 db.session.commit()
 return jsonify(cfg())

@app.post("/api/readings")
def ingest():
 if not device_ok(): return jsonify(error="Unauthorized device"),401
 data=request.get_json(silent=True) or {}
 try: t=float(data["temperature"]); p=float(data["ph"]); tu=float(data["turbidity"])
 except (KeyError,TypeError,ValueError): return jsonify(error="temperature, ph and turbidity are required"),400
 if not all(x==x and abs(x)<100000 for x in (t,p,tu)): return jsonify(error="Invalid numeric reading"),400
 r=Reading(temperature=t,ph=p,turbidity=tu)
 db.session.add(r)
 problems=evaluate(r,cfg())
 for n,v,l,m in problems: db.session.add(Alert(sensor=n,value=v,level=l,message=m))
 db.session.commit()
 return jsonify(ok=True,reading=rd(r),analysis=analyze(r,cfg()),alerts=[{"sensor":x[0],"value":x[1],"level":x[2],"message":x[3]} for x in problems])

@app.cli.command("init-db")
def init_db():
 db.create_all()
 for k,v in DEFAULTS.items():
  if not Setting.query.filter_by(key=k).first(): db.session.add(Setting(key=k,value=v))
 db.session.commit()
 print("AquaSentinel database initialized.")

with app.app_context(): db.create_all()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)),debug=True)
