import {CANTES, scoreHand, totalScores} from './anotador-rules.js';
const $=id=>document.getElementById(id), KEY='bolot_anotador_v1';
let match={version:1,names:['Nosotros','Ellos'],goal:1500,hands:[]};
let editing=null, bidder=0, teamCounts=[[0,0,0,0,0],[0,0,0,0,0]], bolot=[0,0], capoteTeam=null, storageOK=true;
try{const saved=JSON.parse(localStorage.getItem(KEY)||'null');if(saved?.version===1&&Array.isArray(saved.names)&&saved.names.length===2&&saved.names.every(n=>typeof n==='string'&&n.length<=24)&&[1000,1500].includes(saved.goal)&&Array.isArray(saved.hands)){saved.hands.forEach(scoreHand);match=saved;}}catch{storageOK=false;}
$('name-a').value=match.names[0];$('name-b').value=match.names[1];$('goal').value=match.goal;
function show(screen){['home','board','hand-form'].forEach(id=>$(id).hidden=id!==screen);window.scrollTo(0,0);if(screen==='home')renderHome();}
function renderHome(){const n=match.hands.length;$('continue-game').disabled=!n;$('home-note').textContent=n?`Partida guardada: ${n} ${n===1?'mano':'manos'}.`:'No hay ninguna partida guardada.';}
function persist(){try{localStorage.setItem(KEY,JSON.stringify(match));storageOK=true;}catch{storageOK=false;}$('save-status').textContent=storageOK?'Guardado en este móvil':'No se puede guardar en este navegador';}
function draft(){
 const pointsA=$('cards-a').value===''?NaN:Number($('cards-a').value), capote=capoteTeam;
 if(!Number.isInteger(pointsA)||pointsA<0||pointsA>162)throw Error('Introduce un número entero de 0 a 162, incluyendo las últimas y sin cantes.');
 const active=teamCounts.map(c=>c.some(Boolean));let canteTeam=active[0]&&active[1]?$('cante-team').value:active[0]?'0':active[1]?'1':'none';
 if(active[0]&&active[1]&&canteTeam==='none')throw Error('Selecciona quién ganó el choque de cantes.');
 const last=capote!==null?capote:pointsA>=10?0:1;
 return {bidder,cardsA:pointsA-(last===0?10:0),last,capote,canteTeam,counts:canteTeam==='none'?[0,0,0,0,0]:[...teamCounts[Number(canteTeam)]],bolot:[...bolot],pointsA,teamCounts:teamCounts.map(c=>[...c])};
}
function chip(text,label,fn){const b=document.createElement('button');b.type='button';b.className='chip';b.textContent=text;b.setAttribute('aria-label',label);b.onclick=fn;return b;}
function renderEntry(){
 $('en-a').textContent=match.names[0];$('en-b').textContent=match.names[1];
 [0,1].forEach(t=>{const x=t===0?'a':'b';$('cantes-'+x).replaceChildren();
  CANTES.forEach((c,i)=>{const b=document.createElement('button');b.type='button';b.textContent=i===0?'Tercera +20':i===1?'Cincuenta +50':`+${c.points}`;b.setAttribute('aria-label',`Añadir ${c.label} a ${match.names[t]}`);b.disabled=teamCounts[t][i]>=8;b.onclick=()=>{teamCounts[t][i]++;updatePreview();};$('cantes-'+x).append(b);});
  const added=$('added-'+x);added.replaceChildren();
  CANTES.forEach((c,i)=>{if(teamCounts[t][i])added.append(chip(`${c.label} ×${teamCounts[t][i]} ×`,`Quitar ${c.label} de ${match.names[t]}`,()=>{teamCounts[t][i]--;updatePreview();}));});
  if(bolot[t])added.append(chip('Bolot +20 ×',`Quitar bolot de ${match.names[t]}`,()=>{bolot[t]=0;updatePreview();}));
 });
 document.querySelectorAll('[data-bidder]').forEach(b=>{const on=Number(b.dataset.bidder)===bidder;b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(on));});
 document.querySelectorAll('[data-bolot]').forEach(b=>{const on=bolot[Number(b.dataset.bolot)]===1;b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(on));});
 document.querySelectorAll('[data-capote]').forEach(b=>{const on=capoteTeam===Number(b.dataset.capote);b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(on));});
 const both=teamCounts[0].some(Boolean)&&teamCounts[1].some(Boolean);$('clash-field').hidden=!both;
 $('cante-team').querySelector('[value="0"]').textContent=match.names[0];$('cante-team').querySelector('[value="1"]').textContent=match.names[1];
 $('cards-a').disabled=capoteTeam!==null;$('cards-b-input').disabled=capoteTeam!==null;
}
function updatePreview(){
 renderEntry();
 try{const h=draft(),r=scoreHand(h);$('preview-a').textContent=r.awarded[0];$('preview-b').textContent=r.awarded[1];$('preview-note').textContent=r.placed?`${match.names[bidder]} están puestos. Sus cantes se pierden.`:h.capote!==null?'Capote: +100, sin las 10 de últimas.':'162 puntos entre las parejas. Los cantes se suman aparte.';$('save-hand').disabled=false;}
 catch(e){$('preview-a').textContent='-';$('preview-b').textContent='-';$('preview-note').textContent=$('cards-a').value===''?'Introduce los puntos en cualquiera de las dos columnas.':e.message;$('save-hand').disabled=true;}
}
function renderMatch(){
 const total=totalScores(match.hands);
 [0,1].forEach(i=>{const x=i===0?'a':'b';$(`score-${x}`).textContent=total[i];$(`remaining-${x}`).textContent=total[i]>=match.goal?'Objetivo alcanzado':`A ${match.goal-total[i]} de ganar`;});
 const reached=total.map((p,i)=>p>=match.goal?match.names[i]:null).filter(Boolean);$('winner').hidden=!reached.length;$('winner').textContent=reached.length===2?'Las dos parejas han alcanzado el objetivo. Confirmad el ganador en la mesa.':reached.length?`${reached[0]} han alcanzado ${match.goal} puntos. ¡Partida terminada!`:'';
 $('hand-count').textContent=`${match.hands.length} ${match.hands.length===1?'mano':'manos'}`;$('undo').hidden=!match.hands.length;$('history-list').replaceChildren();
 if(!match.hands.length){const p=document.createElement('p');p.className='empty';p.textContent='Las manos guardadas aparecerán aquí. Toca una para modificarla.';$('history-list').append(p);}
 [...match.hands].reverse().forEach((h,k)=>{const i=match.hands.length-1-k,r=scoreHand(h),row=document.createElement('button');row.type='button';row.className='history-row';row.setAttribute('aria-label',`Editar mano ${i+1}`);
  const id=document.createElement('span');id.className='hand-id';id.textContent=`Mano ${i+1} · ${match.names[h.bidder]} ha ido${r.placed?' · Puestos':''}${h.capote!==null?` · Capote de ${match.names[h.capote]}`:''}`;
  const a=document.createElement('strong');a.textContent=r.awarded[0];const b=document.createElement('strong');b.textContent=r.awarded[1];
  const d=document.createElement('span');d.className='detail';d.textContent=`Cartas ${r.cards[0]} / ${r.cards[1]} · Cantes ${r.cantes[0]} / ${r.cantes[1]}`;const ed=document.createElement('span');ed.className='edit';ed.textContent='Editar ›';
  row.append(id,a,b,d,ed);row.onclick=()=>editHand(i);$('history-list').append(row);});
}
function openEntry(){$('hand-title').textContent=editing===null?`Apuntar mano ${match.hands.length+1}`:`Editar mano ${editing+1}`;$('error').hidden=true;show('hand-form');updatePreview();}
function resetForm(){editing=null;bidder=0;teamCounts=[[0,0,0,0,0],[0,0,0,0,0]];bolot=[0,0];capoteTeam=null;$('cards-a').value='';$('cards-b-input').value='';$('cante-team').value='none';}
function closeEntry(){resetForm();renderMatch();show('board');}
function editHand(i){const h=match.hands[i];resetForm();editing=i;bidder=h.bidder;teamCounts=h.teamCounts?h.teamCounts.map(c=>[...c]):[[0,0,0,0,0],[0,0,0,0,0]];if(!h.teamCounts&&h.canteTeam!=='none')teamCounts[Number(h.canteTeam)]=[...h.counts];bolot=[...h.bolot];capoteTeam=h.capote;const p=h.cardsA+(h.last===0?10:0);$('cards-a').value=p;$('cards-b-input').value=162-p;$('cante-team').value=h.canteTeam;openEntry();}
['cards-a','cards-b-input'].forEach((id,i)=>$(id).addEventListener('input',()=>{const v=$(id).value,n=Number(v),other=$(i===0?'cards-b-input':'cards-a');other.value=v!==''&&Number.isInteger(n)&&n>=0&&n<=162?162-n:'';updatePreview();}));
document.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{if(capoteTeam!==null)return;$('cards-a').value='';$('cards-b-input').value='';updatePreview();});
document.querySelectorAll('[data-capote]').forEach(b=>b.onclick=()=>{const t=Number(b.dataset.capote);if(capoteTeam===t){capoteTeam=null;$('cards-a').value='';$('cards-b-input').value='';}else{capoteTeam=t;$('cards-a').value=t===0?162:0;$('cards-b-input').value=t===0?0:162;}updatePreview();});
$('cante-team').onchange=updatePreview;
document.querySelectorAll('[data-bidder]').forEach(b=>b.onclick=()=>{bidder=Number(b.dataset.bidder);updatePreview();});
document.querySelectorAll('[data-bolot]').forEach(b=>b.onclick=()=>{const t=Number(b.dataset.bolot);bolot[t]=1-bolot[t];if(bolot[t])bolot[1-t]=0;updatePreview();});
$('hand-form').onsubmit=e=>{e.preventDefault();try{const h=draft();scoreHand(h);if(editing===null)match.hands.push(h);else match.hands[editing]=h;persist();closeEntry();}catch(err){$('error').textContent=err.message;$('error').hidden=false;}};
$('cancel-edit').onclick=closeEntry;
$('insert').onclick=()=>{resetForm();openEntry();};
$('undo').onclick=()=>{if(confirm(`¿Borrar la mano ${match.hands.length}? Se descontará del marcador.`)){match.hands.pop();persist();renderMatch();}};
$('new-game').onclick=()=>{if(match.hands.length&&!confirm('¿Empezar otra partida? Se borrarán el marcador y las manos guardadas.'))return;match.hands=[];persist();resetForm();renderMatch();show('board');};
$('continue-game').onclick=()=>{renderMatch();show('board');};
$('back-home').onclick=()=>show('home');
['name-a','name-b'].forEach((id,i)=>$(id).addEventListener('change',()=>{match.names[i]=$(id).value.trim()||(i===0?'Nosotros':'Ellos');$(id).value=match.names[i];persist();renderMatch();}));
$('goal').onchange=()=>{match.goal=Number($('goal').value);persist();renderMatch();};
renderMatch();renderHome();$('save-status').textContent=storageOK?'Guardado en este móvil':'No se pudo recuperar la partida guardada';

