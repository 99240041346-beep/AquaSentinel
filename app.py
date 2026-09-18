import os, secrets
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify, session, redirect, render_template, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

app=Flask(__name__)
app.config["SECRET_KEY"]=os.getenv("SECRET_KEY",secrets.token_hex(32))
db_url=os.getenv("DATABASE_URL","sqlite:///aquasentinel.db").replace("postgres://","postgresql://",1)
app.config["SQLALCHEMY_DATABASE_URI"]=db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
db=SQLAlchemy(app)

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True); username=db.Column(db.String(80),unique=True,nullable=False); password_hash=db.Column(db.String(255),nullable=False)
class Reading(db.Model):
    id=db.Column(db.Integer,primary_key=True); temperature=db.Column(db.Float,nullable=False); ph=db.Column(db.Float,nullable=False); turbidity=db.Column(db.Float,nullable=False); created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),index=True)
class Setting(db.Model):
    id=db.Column(db.Integer,primary_key=True); key=db.Column(db.String(80),unique=True,nullable=False); value=db.Column(db.Float,nullable=False)
class Alert(db.Model):
    id=db.Column(db.Integer,primary_key=True); sensor=db.Column(db.String(30),nullable=False); value=db.Column(db.Float,nullable=False); level=db.Column(db.String(20),nullable=False); message=db.Column(db.String(255),nullable=False); created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),index=True)

DEFAULTS={"temp_min":20.0,"temp_max":32.0,"ph_min":6.5,"ph_max":8.5,"turbidity_max":50.0}
def logged_in(): return bool(session.get("user_id"))
def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not logged_in(): return redirect("/login")
        return f(*a,**k)
    return w
def device_ok(): return secrets.compare_digest(request.headers.get("X-Device-Key",""),os.getenv("DEVICE_API_KEY",""))
def settings():
    out=DEFAULTS.copy()
    for s in Setting.query.all(): out[s.key]=s.value
    return out
def evaluate(r,s):
    checks=[("temperature",r.temperature,s["temp_min"],s["temp_max"],"Temperature outside configured range"),
            ("ph",r.ph,s["ph_min"],s["ph_max"],"pH outside configured range"),
            ("turbidity",r.turbidity,0,s["turbidity_max"],"Turbidity above configured maximum")]
    return [(n,v,"CRITICAL",msg) for n,v,lo,hi,msg in checks if v<lo or v>hi]

@app.route("/")
@login_required
def dashboard(): return render_template("dashboard.html")
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=User.query.filter_by(username=request.form.get("username","").strip()).first()
        if u and check_password_hash(u.password_hash,request.form.get("password","")):
            session["user_id"]=u.id; return redirect("/")
        flash("Invalid username or password")
    return render_template("login.html")
@app.post("/logout")
def logout(): session.clear(); return redirect("/login")

@app.get("/api/readings/latest")
@login_required
def latest():
    r=Reading.query.order_by(Reading.created_at.desc()).first()
    return jsonify(reading(r),settings()) if r else jsonify({"reading":None,"settings":settings()})
@app.get("/api/readings")
@login_required
def readings():
    limit=min(int(request.args.get("limit",100)),500)
    rows=Reading.query.order_by(Reading.created_at.desc()).limit(limit).all()
    return jsonify([reading(r) for r in reversed(rows)])
@app.get("/api/alerts")
@login_required
def alerts():
    return jsonify([{"sensor":a.sensor,"value":a.value,"level":a.level,"message":a.message,"created_at":a.created_at.isoformat()} for a in Alert.query.order_by(Alert.created_at.desc()).limit(50)])
@app.get("/api/settings")
@login_required
def get_settings(): return jsonify(settings())
@app.post("/api/settings")
@login_required
def save_settings():
    data=request.get_json(force=True)
    for k in DEFAULTS:
        if k in data:
            try: v=float(data[k])
            except: continue
            s=Setting.query.filter_by(key=k).first() or Setting(key=k)
            s.value=v; db.session.add(s)
    db.session.commit(); return jsonify(settings())
@app.post("/api/readings")
def ingest():
    if not device_ok(): return jsonify({"error":"Unauthorized device"}),401
    data=request.get_json(force=True)
    try: t=float(data["temperature"]); p=float(data["ph"]); tu=float(data["turbidity"])
    except (KeyError,TypeError,ValueError): return jsonify({"error":"temperature, ph and turbidity are required"}),400
    r=Reading(temperature=t,ph=p,turbidity=tu); db.session.add(r)
    s=settings()
    for n,v,level,msg in evaluate(r,s): db.session.add(Alert(sensor=n,value=v,level=level,message=msg))
    db.session.commit()
    return jsonify({"ok":True,"reading":reading(r),"alerts":[x[0] for x in evaluate(r,s)]})
def reading(r):
    return {"temperature":r.temperature,"ph":r.ph,"turbidity":r.turbidity,"created_at":r.created_at.isoformat()}

@app.cli.command("init")
def init():
    db.create_all()
    if not User.query.first():
        username=os.getenv("ADMIN_USERNAME","admin"); password=os.getenv("ADMIN_PASSWORD","change-me")
        db.session.add(User(username=username,password_hash=generate_password_hash(password)))
    for k,v in DEFAULTS.items():
        if not Setting.query.filter_by(key=k).first(): db.session.add(Setting(key=k,value=v))
    db.session.commit(); print("AquaSentinel initialized.")
@app.get("/health")
def health(): return jsonify({"status":"ok"})
with app.app_context(): db.create_all()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)),debug=True)
