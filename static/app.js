let cfg={};let seen=new Set();let ready=false;
let chart=new Chart(document.getElementById("chart"),{type:"line",data:{labels:[],datasets:[{label:"Temperature °C",data:[]},{label:"pH",data:[]},{label:"Turbidity NTU",data:[]}]},options:{responsive:true,interaction:{mode:"index",intersect:false}}});
const $=id=>document.getElementById(id);const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function setStatus(id,status){$(id).textContent=status;$(id).className=status==="NORMAL"?"ok":status==="WARNING"?"warn":"bad"}
async function load(){
 try{
  let [r,s,a,an]=await Promise.all([fetch("/api/readings?limit=100"),fetch("/api/settings"),fetch("/api/alerts"),fetch("/api/analysis")]);
  if(!r.ok||!s.ok||!a.ok||!an.ok)throw Error();
  let rows=await r.json();cfg=await s.json();let alerts=await a.json();let analysis=await an.json();
  let online=analysis.online===true;
  $("connection").textContent=online?"● Online":"● Offline";$("connection").className=online?"pill ok":"pill warn";
  $("overallStatus").textContent=analysis.overall;$("overallStatus").className=analysis.overall==="NORMAL"?"pill ok":analysis.overall==="WARNING"?"pill warn":"pill bad";
  $("analysisMessage").textContent=analysis.message||"Automatic analysis is running.";
  Object.keys(cfg).forEach(k=>{if($(k))$(k).value=cfg[k]});
  if(analysis.reading){
   let x=analysis.reading;
   $("temp").textContent=x.temperature.toFixed(2)+" °C";$("ph").textContent=x.ph.toFixed(2);$("turbidity").textContent=x.turbidity.toFixed(2)+" NTU";
   let by=Object.fromEntries((analysis.sensors||[]).map(x=>[x.sensor.toLowerCase(),x.status]));
   setStatus("tempStatus",by.temperature||"NORMAL");setStatus("phStatus",by.ph||"NORMAL");setStatus("turbidityStatus",by.turbidity||"NORMAL");
  }else{$("temp").textContent="-- °C";$("ph").textContent="--";$("turbidity").textContent="--";["tempStatus","phStatus","turbidityStatus"].forEach(id=>{$(id).textContent="Waiting";$(id).className=""})}
  chart.data.labels=rows.map(x=>new Date(x.created_at).toLocaleTimeString());chart.data.datasets[0].data=rows.map(x=>x.temperature);chart.data.datasets[1].data=rows.map(x=>x.ph);chart.data.datasets[2].data=rows.map(x=>x.turbidity);chart.update();
  $("alertCount").textContent=alerts.length;$("alerts").innerHTML=alerts.length?alerts.map(a=>'<div class="alert"><b class="bad">'+esc(a.level)+"</b> • "+esc(a.sensor)+" = "+a.value+'<br><span class="muted">'+esc(a.message)+" • "+new Date(a.created_at).toLocaleString()+"</span></div>").join(""):"No alerts";
  if(ready&&"Notification"in window)alerts.filter(a=>!seen.has(a.id)).forEach(a=>{if(Notification.permission==="granted")new Notification("AquaSentinel alert",{body:a.sensor+": "+a.value+" — "+a.message})});
  alerts.forEach(a=>seen.add(a.id));ready=true;
 }catch(e){$("connection").textContent="● Offline";$("connection").className="pill warn";$("overallStatus").textContent="OFFLINE";$("overallStatus").className="pill warn";$("analysisMessage").textContent="Dashboard cannot reach the AquaSentinel server."}
}
$("notifyBtn").onclick=async()=>{if(!("Notification"in window))return alert("Notifications are not supported by this browser.");let p=await Notification.requestPermission();$("notifyBtn").textContent=p==="granted"?"Notifications enabled":"Enable notifications"};
$("saveBtn").onclick=async()=>{let d={};Object.keys(cfg).forEach(k=>{if($(k))d[k]=Number($(k).value)});await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(d)});$("saveMsg").textContent="Thresholds saved";setTimeout(()=>$("saveMsg").textContent="",2000);load()};
load();setInterval(load,5000);