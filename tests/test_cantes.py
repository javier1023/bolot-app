import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from models import game as g
from models.deck import Carta, Palo, Valor
import testeo


def seq(j, suit, top):
    values = g.SECUENCIA_CANTES[top-2:top+1]
    return g.Cante('tercera',20,[Carta(suit,v) for v in values],j)


def fixture(winner=0):
    e=g.nueva_partida(dealer=3);e.fase=g.Fase.BAZAS;e.triunfo=Palo.BASTOS;e.turno=0
    e.cantes_anunciados={0:[seq(0,Palo.COPAS,6 if winner==0 else 2)],1:[seq(1,Palo.OROS,2 if winner==0 else 6)]}
    e.baza_actual=g.Baza(cartas=[(j,Carta(Palo.ESPADAS,v)) for j,v in enumerate([Valor.AS,Valor.SIETE,Valor.OCHO,Valor.NUEVE])])
    g._resolver_baza(e)
    return e


def test_reproduce_previous_bug():
    # Before the fix, ensenar_cantes accepted both teams, and the visible map
    # contained two opposing terceras. This assertion is the regression gate.
    e=fixture();e.turno=1;g.ensenar_cantes(e,1)
    assert e.error and not e.cantes_ensenados


def test_winner_reveal_and_points():
    e=fixture();e.turno=0;g.ensenar_cantes(e,0)
    assert not e.error and set(e.cantes_ensenados)=={0}
    e.turno=1;g.ensenar_cantes(e,1)
    assert e.error and set(e.cantes_ensenados)=={0}
    g._procesar_cantes_pre_segunda(e)
    assert e.cantes_equipo==[20,0]
    assert [c.jugador for c in e.cantes]==[0]
    assert not e.cantes_ensenados and not e.cantes_anunciados


def test_forgotten_winner_does_not_transfer_right():
    e=fixture();e.turno=0;e.cantes_anunciados.pop(0)
    e.turno=1;g.ensenar_cantes(e,1)
    g._procesar_cantes_pre_segunda(e)
    assert e.cantes_equipo==[0,0]


def test_partner_and_snapshot():
    e=fixture();e.cantes_anunciados[2]=[seq(2,Palo.ESPADAS,2)]
    for j in [0,2]:
        e.turno=j;assert g.puede_ensenar_cantes(e,j);g.ensenar_cantes(e,j)
    g._procesar_cantes_pre_segunda(e)
    assert e.cantes_equipo==[40,0]


def test_comparison_and_ties():
    a=seq(0,Palo.COPAS,6);b=seq(1,Palo.OROS,2)
    assert g._resolver_cantes_todos([[a],[b]],Palo.BASTOS,1)==0
    b=seq(1,Palo.BASTOS,6)
    assert g._resolver_cantes_todos([[a],[b]],Palo.BASTOS,0)==1
    b=seq(1,Palo.OROS,6)
    assert g._resolver_cantes_todos([[a],[b]],Palo.BASTOS,1)==1
    a=g.Cante('cien_seq',100,a.cartas,0);b=g.Cante('cien_cuatro',100,b.cartas,1)
    assert g._resolver_cantes_todos([[a],[b]],Palo.BASTOS,0)==1
    assert g._resolver_cantes_todos([[],[]],Palo.BASTOS,0) is None


def test_observation_privacy_and_testeo():
    e=fixture();e.turno=0;g.ensenar_cantes(e,0)
    for actor in range(4):
        o=testeo.observation(e,actor)
        assert set(o['cantes_ensenados'])=={'0'}
        assert isinstance(o['manos'][actor],list)
        assert all(isinstance(o['manos'][j],int) for j in range(4) if j!=actor)
    e.turno=1;assert not testeo.serialize(e)['puede_ensenar_cantes']
    e.turno=2;e.cantes_anunciados[2]=[seq(2,Palo.ESPADAS,2)]
    assert testeo.serialize(e)['puede_ensenar_cantes']


def test_bolot_losing_team_still_scores():
    e=fixture();e.turno=1;e.manos[1]=[Carta(Palo.BASTOS,Valor.CABALLO),Carta(Palo.BASTOS,Valor.REY)]
    g.declarar_bolot(e,1);assert not e.error
    g._procesar_cantes_pre_segunda(e)
    assert e.cantes_equipo==[0,20]

