import sys,json,random,subprocess
from types import SimpleNamespace
sys.path.insert(0,'backend')
from models.game import _fin_mano
random.seed(4)
cases=[]
for _ in range(4000):
 cap=random.choice([None,None,None,0,1]); c=random.randrange(153) if cap is None else (152 if cap==0 else 0)
 h=dict(bidder=random.randrange(2),cardsA=c,last=random.randrange(2) if cap is None else cap,capote=cap,canteTeam=random.choice(['none','0','1']),counts=[random.randrange(3) for _ in range(5)],bolot=random.choice([[0,0],[1,0],[0,1]]))
 if h['canteTeam']=='none': h['counts']=[0]*5
 ce=[n*20 for n in h['bolot']]
 if h['canteTeam']!='none':ce[int(h['canteTeam'])]+=sum(n*p for n,p in zip(h['counts'],[20,50,100,150,200]))
 pm=[c,152-c];pm[h['last']]+=10
 bazas=[SimpleNamespace(ganador=cap if cap is not None else i%2) for i in range(8)]
 state=SimpleNamespace(quien_va=h['bidder'],bazas_jugadas=bazas,puntos_mano=pm,cantes_equipo=ce,puntos_totales=[0,0])
 _fin_mano(state);cases.append(dict(hand=h,expected=state.puntos_totales))
js="import{scoreHand}from './frontend/js/anotador-rules.js';let s='';for await(const c of process.stdin)s+=c;const a=JSON.parse(s);for(const x of a)if(JSON.stringify(scoreHand(x.hand).awarded)!==JSON.stringify(x.expected))throw Error(JSON.stringify(x));console.log(a.length+' differential cases match Python engine');"
subprocess.run(['node','--input-type=module','-e',js],input=json.dumps(cases),text=True,check=True)

