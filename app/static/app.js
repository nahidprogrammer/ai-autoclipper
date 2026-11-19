let selectedFile=null, currentJob=null, totalClips=0;
const $=id=>document.getElementById(id);
const fileInput=$("videoFile");
fileInput.addEventListener("change",()=>{selectedFile=fileInput.files[0];$("fileName").textContent=selectedFile?selectedFile.name:"No file selected";checkReady()});
$("authorized").addEventListener("change",checkReady);
function checkReady(){$("analyzeBtn").disabled=!(selectedFile && $("authorized").checked)}
function progress(p,msg){$("progressWrap").style.display="block";$("progressBar").style.width=p+"%";$("statusText").textContent=msg}
$("analyzeBtn").addEventListener("click",async()=>{
 try{
  $("analyzeBtn").disabled=true;progress(10,"Uploading video securely to your local workspace…");
  const fd=new FormData();fd.append("file",selectedFile);fd.append("authorized","true");
  let r=await fetch("/api/upload",{method:"POST",body:fd});let data=await r.json();if(!r.ok)throw Error(data.detail||"Upload failed");currentJob=data.id;
  progress(40,"Transcribing speech and analyzing potential highlights…");
  const af=new FormData();af.append("count",$("targetClips").value);
  r=await fetch(`/api/analyze/${currentJob}`,{method:"POST",body:af});data=await r.json();if(!r.ok)throw Error(data.detail||"Analysis failed");
  totalClips=data.clips.length;$("projectCount").textContent="1";$("generatedCount").textContent=totalClips;
  $("resultMeta").textContent=`${totalClips} suggestions · ${data.mode==="AI"?"AI-selected":"fallback suggestions"}`;
  renderClips(data.clips,data.mode);progress(100,data.mode==="AI"?"AI analysis complete. Review your clips.":"Suggestions ready. Add Gemini and Whisper configuration for AI-selected highlights.");
 }catch(e){progress(100,"Error: "+e.message)}finally{$("analyzeBtn").disabled=false}
});
function renderClips(clips,mode){
 const root=$("clips");root.innerHTML="";
 clips.forEach((c,i)=>{
  const el=document.createElement("article");el.className="clip";
  const start=Number(c.start).toFixed(1),end=Number(c.end).toFixed(1);
  el.innerHTML=`<div class="clip-top">▶</div><div class="clip-body"><b></b><p></p><div class="clip-meta"><span>${start}s – ${end}s</span><span>${c.score||"—"}/100</span></div><div class="clip-actions"><button class="render">Render 9:16</button><button class="secondary download" disabled>Download</button></div></div>`;
  el.querySelector("b").textContent=c.title||`Clip ${i+1}`;el.querySelector("p").textContent=c.reason||"Suggested highlight";
  const render=el.querySelector(".render"),download=el.querySelector(".download");
  render.onclick=async()=>{render.disabled=true;render.textContent="Rendering…";try{const fd=new FormData();const res=await fetch(`/api/render/${currentJob}/${i}`,{method:"POST",body:fd});const out=await res.json();if(!res.ok)throw Error(out.detail);download.disabled=false;download.onclick=()=>window.open(out.url,"_blank");render.textContent="Rendered ✓"}catch(e){render.textContent="Retry render";alert(e.message)}finally{render.disabled=false}};
  root.appendChild(el);
 });
}
fetch("/api/health").then(r=>r.json()).then(d=>{$("engineStatus").textContent=d.ffmpeg?"Ready":"Install FFmpeg"}).catch(()=>{$("engineStatus").textContent="Offline"});
