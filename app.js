const cities=[
 {id:"Sapporo",name:"삿포로",country:"JP",lat:43.0618,lon:141.3545,night:8,transit:8,baseTemp:15,plan:["오도리공원·삿포로역","니조시장·스스키노","오타루 당일치기","모이와야마·맥주박물관"]},
 {id:"Sendai",name:"센다이",country:"JP",lat:38.2682,lon:140.8694,night:7,transit:8,baseTemp:18,plan:["센다이역·아케이드","마쓰시마","아오바성·고쿠분초","시장·역 주변 쇼핑"]},
 {id:"Tokyo",name:"도쿄",country:"JP",lat:35.6762,lon:139.6503,night:10,transit:10,baseTemp:22,plan:["우에노·아메요코","아사쿠사·스카이트리","아키하바라·긴자","신주쿠·가부키초"]},
 {id:"Fukuoka",name:"후쿠오카",country:"JP",lat:33.5902,lon:130.4017,night:9,transit:9,baseTemp:23,plan:["하카타·텐진","다자이후","나카스·캐널시티","모모치·야타이"]},
 {id:"Osaka",name:"오사카",country:"JP",lat:34.6937,lon:135.5023,night:10,transit:9,baseTemp:23,plan:["난바·도톤보리","우메다","덴덴타운·신세카이","오사카성·텐노지"]},
 {id:"Taipei",name:"타이베이",country:"TW",lat:25.033,lon:121.5654,night:9,transit:9,baseTemp:25,plan:["시먼딩·용산사","중산·다다오청","지우펀·스펀","신이·타이베이101"]},
 {id:"Beijing",name:"베이징",country:"CN",lat:39.9042,lon:116.4074,night:7,transit:8,baseTemp:20,plan:["왕푸징","자금성·천안문","만리장성","싼리툰"]},
 {id:"Shanghai",name:"상하이",country:"CN",lat:31.2304,lon:121.4737,night:9,transit:9,baseTemp:23,plan:["난징동루·와이탄","프랑스조계","루자쭈이","신천지"]},
];

const $=s=>document.querySelector(s);
const fmt=n=>new Intl.NumberFormat("ko-KR").format(n);
const today=new Date();
const iso=d=>{const x=new Date(d);x.setMinutes(x.getMinutes()-x.getTimezoneOffset());return x.toISOString().slice(0,10)};
$("#startDate").value=iso(new Date(today.getTime()+1000*60*60*24*14));
$("#endDate").value=iso(new Date(today.getTime()+1000*60*60*24*60));

$("#cityChecks").innerHTML=cities.map((c,i)=>`<label class="chip"><input type="checkbox" value="${c.id}" ${i<5?"checked":""}><span>${c.name}</span></label>`).join("");
["heat","rain","night","transit"].forEach(id=>$("#"+id).addEventListener("input",e=>$("#"+id+"V").textContent=e.target.value));

$("#presetBtn").onclick=()=>{$("#heat").value=10;$("#rain").value=9;$("#night").value=10;$("#transit").value=8;["heat","rain","night","transit"].forEach(id=>$("#"+id+"V").textContent=$("#"+id).value)};

function datePairs(start,end,nights){
 const out=[]; let d=new Date(start+"T00:00:00"); const last=new Date(end+"T00:00:00");
 while(d<=last && out.length<45){const ret=new Date(d);ret.setDate(ret.getDate()+Number(nights)+1);out.push({depart:iso(d),return:iso(ret),weekend:[0,5,6].includes(d.getDay())});d.setDate(d.getDate()+1)}
 return out;
}
async function weatherFor(c,date){
 const days=(new Date(date)-new Date())/86400000;
 if(days>=0 && days<=15){
  const u=`https://api.open-meteo.com/v1/forecast?latitude=${c.lat}&longitude=${c.lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum&timezone=auto&start_date=${date}&end_date=${date}`;
  const r=await fetch(u); if(r.ok){const j=await r.json(); return {kind:"예보",max:j.daily.temperature_2m_max?.[0],min:j.daily.temperature_2m_min?.[0],rain:j.daily.precipitation_probability_max?.[0]??0,precip:j.daily.precipitation_sum?.[0]??0}}
 }
 return {kind:"계절 참고",max:c.baseTemp+4,min:c.baseTemp-4,rain:null,precip:null};
}
function scoreCity(c,w,p){
 const heatTarget=20; const heatScore=Math.max(0,10-Math.abs((w.max??c.baseTemp)-heatTarget)*.65);
 const rainScore=w.rain==null?6:Math.max(0,10-w.rain/10);
 const total=(heatScore*p.heat + rainScore*p.rain + c.night*p.night + c.transit*p.transit)/(p.heat+p.rain+p.night+p.transit||1)*10;
 return Math.round(total);
}
function flightLink(origin,c,depart,ret){
 const q=encodeURIComponent(`${origin} to ${c.name} ${depart} ${ret} flights`);
 return `https://www.google.com/travel/flights?q=${q}`;
}
function reason(c,w,p){
 const bits=[];
 if((w.max??99)<=24 && p.heat>=7)bits.push("기온 조건이 선호에 비교적 잘 맞음");
 if(c.night>=9 && p.night>=7)bits.push("밤 산책·술집 선택지가 많은 편");
 if(c.transit>=9 && p.transit>=7)bits.push("대중교통 이동이 편한 편");
 if(w.rain!=null && w.rain<=30)bits.push("조회된 강수확률이 낮은 편");
 return bits.length?bits.join(" · "):"입력한 가중치를 종합한 후보";
}
$("#searchBtn").onclick=async()=>{
 const selected=[...document.querySelectorAll("#cityChecks input:checked")].map(x=>x.value);
 if(!selected.length)return alert("후보 도시를 하나 이상 선택하세요.");
 const start=$("#startDate").value,end=$("#endDate").value,nights=$("#nights").value;
 if(!start||!end||new Date(start)>new Date(end))return alert("날짜 범위를 확인하세요.");
 const pairs=datePairs(start,end,nights);
 const p={heat:+$("#heat").value,rain:+$("#rain").value,night:+$("#night").value,transit:+$("#transit").value};
 $("#loading").classList.remove("hidden");$("#resultsWrap").classList.add("hidden");$("#planWrap").classList.add("hidden");
 try{
  const chosen=cities.filter(c=>selected.includes(c.id));
  const samplePairs=[pairs[0],pairs[Math.floor(pairs.length/2)],pairs[pairs.length-1]].filter((v,i,a)=>v&&a.findIndex(x=>x.depart===v.depart)===i);
  const rows=[];
  for(const c of chosen){
   let best=null;
   for(const pair of samplePairs){
    const w=await weatherFor(c,pair.depart);
    const s=scoreCity(c,w,p);
    if(!best||s>best.score)best={city:c,pair,w,score:s};
   }
   rows.push(best);
  }
  rows.sort((a,b)=>b.score-a.score);
  $("#results").innerHTML=rows.map((r,i)=>`
   <article class="result">
    <div class="result-top"><div><span class="rank">#${i+1}</span><h3>${r.city.name}</h3></div><div class="score">${r.score}<small>/100</small></div></div>
    <div class="meta">
      <span class="pill">${r.pair.depart} → ${r.pair.return}</span>
      <span class="pill">${r.w.kind}</span>
      <span class="pill">${r.w.min}~${r.w.max}℃</span>
      ${r.w.rain==null?"":`<span class="pill">강수확률 ${r.w.rain}%</span>`}
    </div>
    <div class="why">${reason(r.city,r.w,p)}</div>
    <div class="flight"><b>항공권 가격:</b> 실시간 공급자 미연결 — 임의 가격은 표시하지 않음</div>
    <div class="actions"><a href="${flightLink($("#origin").value,r.city,r.pair.depart,r.pair.return)}" target="_blank" rel="noopener">실제 항공권 검색</a><button data-plan="${r.city.id}" data-depart="${r.pair.depart}">일정 만들기</button></div>
   </article>`).join("");
  $("#dataStamp").textContent=`조회 ${new Date().toLocaleString("ko-KR")}`;
  $("#resultsWrap").classList.remove("hidden");
  document.querySelectorAll("[data-plan]").forEach(b=>b.onclick=()=>showPlan(b.dataset.plan,b.dataset.depart));
 }catch(e){alert("날씨 조회 중 오류가 났습니다. 잠시 후 다시 시도하세요.");console.error(e)}
 finally{$("#loading").classList.add("hidden")}
};
function showPlan(id,depart){
 const c=cities.find(x=>x.id===id);const nights=+$("#nights").value;const total=nights+1;
 const items=Array.from({length:total},(_,i)=>{const d=new Date(depart);d.setDate(d.getDate()+i);const area=c.plan[i%c.plan.length];return `<div class="day"><h3>DAY ${i+1} · ${iso(d)}</h3><ul><li>오전: ${area} 중심 가벼운 일정</li><li>점심: 현지 인기 식사 카테고리에서 선택</li><li>오후: 같은 권역 관광·쇼핑</li><li>저녁: 이동거리 짧은 식사 + 밤 산책/술집</li></ul></div>`}).join("");
 $("#plan").innerHTML=`<h2>${c.name} ${nights}박 ${total}일</h2>${items}`;$("#planWrap").classList.remove("hidden");$("#planWrap").scrollIntoView({behavior:"smooth"});
}
$("#closePlan").onclick=()=>$("#planWrap").classList.add("hidden");
