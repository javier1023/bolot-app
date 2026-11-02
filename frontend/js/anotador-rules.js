// Same scoring as backend/models/game.py::_fin_mano.
export const CANTES = [
  {id:'tercera', label:'Tercera', points:20},
  {id:'cincuenta', label:'Cincuenta', points:50},
  {id:'cien', label:'Cien', points:100},
  {id:'nueves', label:'4 nueves', points:150},
  {id:'sotas', label:'4 sotas', points:200},
];
export function scoreHand(hand) {
  const {bidder, cardsA, last, capote, canteTeam, counts, bolot} = hand;
  if (![0,1].includes(bidder) || ![0,1].includes(last) || ![null,0,1].includes(capote)) throw Error('Selecciona quién ha ido y quién hizo las últimas.');
  if (!Number.isInteger(cardsA) || cardsA < 0 || cardsA > 152) throw Error('Los puntos de cartas deben ser un número entero de 0 a 152, sin las últimas ni cantes.');
  if (!['none','0','1'].includes(canteTeam) || !Array.isArray(counts) || counts.length !== 5 || counts.some(n=>!Number.isInteger(n)||n<0||n>8)) throw Error('Revisa los cantes.');
  if (!Array.isArray(bolot) || bolot.length!==2 || bolot.some(n=>![0,1].includes(n)) || bolot[0]+bolot[1]>1) throw Error('Solo puede haber un bolot por mano, en una pareja.');
  if (canteTeam==='none' && counts.some(Boolean)) throw Error('Selecciona la pareja que ganó los cantes.');
  if (capote!==null && (cardsA!==(capote===0?152:0) || last!==capote)) throw Error('En un capote, la misma pareja gana todas las cartas y las últimas.');
  const cards=[cardsA,152-cardsA];
  cards[last]+=10;
  const cantes=bolot.map(n=>n*20);
  if (canteTeam!=='none') cantes[Number(canteTeam)]+=counts.reduce((s,n,i)=>s+n*CANTES[i].points,0);
  const raw=cards.map((p,i)=>p+cantes[i]);
  const placed=raw[bidder]<=raw[1-bidder];
  const awarded=placed?[0,0]:[...raw];
  if (placed) awarded[1-bidder]=162+cantes[1-bidder];
  if (capote!==null && (placed ? capote!==bidder : capote===bidder)) awarded[capote]+=90; // +100, remove 10 for last trick
  return {awarded, placed, cards, cantes, raw, capote};
}
export function totalScores(hands) {
  return hands.reduce((sum,h)=>scoreHand(h).awarded.map((p,i)=>sum[i]+p),[0,0]);
}

