import os,secrets
from datetime import datetime,timezone
from functools import wraps
from flask import Flask,request,jsonify,session,redirect,render_template,flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc
from werkzeug.security import generate_password_hash,check_password_hash

app=Flask(__name__)
app.config.update(SECRET_KEY=os.getenv("SECRET_KEY",secrets.token_hex(32)),SQLALCHEMY_TRACK_MODIFICATIONS=False)
app.config["SQLALCHEMY_DATABASE_URI"]=os.getenv("DATABASE_URL","sqlite:///aquasentinel.db").replace("postgres://","postgresql://",1)
db=SQLAlchemy(app)

DEFAULTS={"temp_min":20.0,"temp_max":32.0,"ph_min":6.5,"ph_max":8.5,"turbidity_max":50.0}
WATER_TYPES=["Freshwater","Brackish","Marine"]
AQUACULTURE_TYPES=["Shrimp Farming","Fish Farming","General Aquaculture"]
WATER_SOURCES=["Farm Pond","Tank","Well","River","Canal","Seawater","Other"]

class User(db.Model):
 id=db.Column(db.Integer,primary_key=True); username=db.Column(db.String(80),unique=True,nullable=False); password_hash=db.Column(db.String(255),nullable=False)
class Reading(db.Model):
 id=db.Column(db.Integer,primary_key=True); temperature=db.Column(db.Float,nullable=False); ph=db.Column(db.Float,nullable=False); turbidity=db.Column(db.Float,nullable=False); created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),index=True)
class Setting(db.Model):
 id=db.Column(db.Integer,primary_key=True); key=db.Column(db.String(80),unique=True,nullable=False); value=db.Column(db.Float,nullable=False)
class WaterProfile(db.Model):
 id=db.Column(db.Integer,primary_key=True); water_type=db.Column(db.String(30),nullable=False,default="Freshwater"); aquaculture_type=db.Column(db.String(40),nullable=False,default="General Aquaculture"); water_source=db.Column(db.String(30),nullable=False,default="Farm Pond"); monitoring_name=db.Column(db.String(80),nullable=False,default="Pond 1"); updated_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),onupdate=lambda:datetime.now(timezone.utc))
class Alert(db.Model):
 id=db.Column(db.Integer,primary_key=True); sensor=db.Column(db.String(30),nullable=False); value=db.Column(db.Float,nullable=False); level=db.Column(db.String(20),nullable=False); message=db.Column(db.String(255),nullable=False); created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),index=True)

def auth(f):
 @wraps(f)
 def w(*a,**k):
  if not session.get("user_id"): return redirect("/login")
  return f(*a,**k)
 return w
def device_ok():
 return bool(os.getenv("DEVICE_API_KEY")) and secrets.compare_digest(request.headers.get("X-Device-Key",""),os.getenv("DEVICE_API_KEY"))
def cfg():
 d=DEFAULTS.copy()
 for x in Setting.query.all(): d[x.key]=x.value
 return d
def profile():
 x=WaterProfile.query.first()
 if not x:
  x=WaterProfile(); db.session.add(x); db.session.commit()
 return x
def profile_json(x):
 return {"water_type":x.water_type,"aquaculture_type":x.aquaculture_type,"water_source":x.water_source,"monitoring_name":x.monitoring_name}
def iso(dt):
 return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).isoformat()
def rd(x):
 return {"id":x.id,"temperature":x.temperature,"ph":x.ph,"turbidity":x.turbidity,"created_at":iso(x.created_at)}
def evaluate(r,c):
 out=[]
 if r.temperature<c["temp_min"] or r.temperature>c["temp_max"]: out.append(("temperature",r.temperature,"CRITICAL","Temperature outside configured range"))
 if r.ph<c["ph_min"] or r.ph>c["ph_max"]: out.append(("ph",r.ph,"CRITICAL","pH outside configured range"))
 if r.turbidity<0 or r.turbidity>c["turbidity_max"]: out.append(("turbidity",r.turbidity,"CRITICAL","Turbidity above configured maximum"))
 return out

@app.get("/health")
def health(): return jsonify(status="ok",service="AquaSentinel")
@app.route("/login",methods=["GET","POST"])
def login():
 if request.method=="POST":
  u=User.query.filter_by(username=request.form.get("username","").strip()).first()
  if u and check_password_hash(u.password_hash,request.form.get("password","")): session["user_id"]=u.id; return redirect("/")
  flash("Invalid username or password")
 return render_template("login.html")
@app.post("/logout")
def logout(): session.clear(); return redirect("/login")
@app.get("/")
@auth
def dashboard(): return render_template("dashboard.html")
@app.get("/api/readings")
@auth
def api_readings():
 try: limit=max(1,min(int(request.args.get("limit",100)),1000))
 except: limit=100
 return jsonify([rd(x) for x in Reading.query.order_by(desc(Reading.created_at)).limit(limit).all()][::-1])
@app.get("/api/readings/latest")
@auth
def latest():
 x=Reading.query.order_by(desc(Reading.created_at)).first()
 return jsonify({"reading":rd(x) if x else None,"settings":cfg(),"profile":profile_json(profile())})
@app.get("/api/alerts")
@auth
def api_alerts():
 return jsonify([{"id":x.id,"sensor":x.sensor,"value":x.value,"level":x.level,"message":x.message,"created_at":iso(x.created_at)} for x in Alert.query.order_by(desc(Alert.created_at)).limit(100).all()])
@app.get("/api/settings")
@auth
def api_settings(): return jsonify(cfg())
@app.post("/api/settings")
@auth
def save_settings():
 data=request.get_json(silent=True) or {}
 for k in DEFAULTS:
  if k in data:
   try: v=float(data[k])
   except: continue
   x=Setting.query.filter_by(key=k).first() or Setting(key=k); x.value=v; db.session.add(x)
 db.session.commit(); return jsonify(cfg())
@app.get("/api/water-profile")
@auth
def get_water_profile():
 x=profile()
 return jsonify({**profile_json(x),"options":{"water_types":WATER_TYPES,"aquaculture_types":AQUACULTURE_TYPES,"water_sources":WATER_SOURCES}})
@app.post("/api/water-profile")
@auth
def save_water_profile():
 data=request.get_json(silent=True) or {}; x=profile()
 wt=str(data.get("water_type",x.water_type)).strip(); aq=str(data.get("aquaculture_type",x.aquaculture_type)).strip(); ws=str(data.get("water_source",x.water_source)).strip(); mn=str(data.get("monitoring_name",x.monitoring_name)).strip()
 if wt not in WATER_TYPES or aq not in AQUACULTURE_TYPES or ws not in WATER_SOURCES or not mn or len(mn)>80: return jsonify(error="Invalid water profile"),400
 x.water_type=wt; x.aquaculture_type=aq; x.water_source=ws; x.monitoring_name=mn; db.session.commit()
 return jsonify(profile_json(x))
@app.post("/api/readings")
def ingest():
 if not device_ok(): return jsonify(error="Unauthorized device"),401
 data=request.get_json(silent=True) or {}
 try: t=float(data["temperature"]); p=float(data["ph"]); tu=float(data["turbidity"])
 except (KeyError,TypeError,ValueError): return jsonify(error="temperature, ph and turbidity are required"),400
 if not all(x==x and abs(x)<100000 for x in (t,p,tu)): return jsonify(error="Invalid numeric reading"),400
 r=Reading(temperature=t,ph=p,turbidity=tu); db.session.add(r); c=cfg(); problems=evaluate(r,c)
 for n,v,l,m in problems: db.session.add(Alert(sensor=n,value=v,level=l,message=m))
 db.session.commit()
 return jsonify(ok=True,reading=rd(r),alerts=[{"sensor":x[0],"value":x[1],"level":x[2],"message":x[3]} for x in problems])
@app.post("/api/test-reading")
@auth
def test_reading():
 data=request.get_json(silent=True) or {}
 try: r=Reading(temperature=float(data["temperature"]),ph=float(data["ph"]),turbidity=float(data["turbidity"]))
 except: return jsonify(error="temperature, ph and turbidity are required"),400
 db.session.add(r); c=cfg()
 for n,v,l,m in evaluate(r,c): db.session.add(Alert(sensor=n,value=v,level=l,message=m))
 db.session.commit(); return jsonify(ok=True,reading=rd(r))

@app.cli.command("init-db")
def init_db():
 db.create_all()
 if not User.query.first(): db.session.add(User(username=os.getenv("ADMIN_USERNAME","admin"),password_hash=generate_password_hash(os.getenv("ADMIN_PASSWORD","change-me"))))
 for k,v in DEFAULTS.items():
  if not Setting.query.filter_by(key=k).first(): db.session.add(Setting(key=k,value=v))
 if not WaterProfile.query.first(): db.session.add(WaterProfile())
 db.session.commit(); print("AquaSentinel database initialized.")

@app.cli.command("reset-admin")
def reset_admin():
 """Reset the admin password using ADMIN_PASSWORD or an interactive prompt."""
 username=os.getenv("ADMIN_USERNAME","admin").strip() or "admin"
 password=os.getenv("ADMIN_PASSWORD","").strip()
 if not password:
  import getpass
  password=getpass.getpass("New admin password: ")
 if len(password)<8:
  print("Password must be at least 8 characters."); return 1
 u=User.query.filter_by(username=username).first()
 if not u:
  u=User(username=username,password_hash=generate_password_hash(password)); db.session.add(u)
 else:
  u.password_hash=generate_password_hash(password)
 db.session.commit()
 print(f"Admin password reset for user: {username}")

with app.app_context(): db.create_all()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)),debug=True)
