from agora import Agora
from agents import Empiricist, Rationalist, Ethicist, Historian, DevilsAdvocate, Pragmatist, Phenomenologist
ListOfAgents = [Empiricist(), Rationalist(), Ethicist(), Historian(), DevilsAdvocate(), Pragmatist(), Phenomenologist()]
Key = open("key.txt").readlines()[0]
Parliament = Agora(Key, ListOfAgents)
Parliament.debate(turns=1)