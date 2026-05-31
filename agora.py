import anthropic
from agents import Agent
from datetime import datetime

class Agora:
	MODEL = "claude-sonnet-4-20250514"
	MAX_TOKENS = 500
	def __init__(self, api_key: str, ListOfAgents = []):
		self.client = anthropic.Anthropic(api_key=api_key)
		self.ListOfAgents = ListOfAgents

	def QueryLLM(self, human_turn: str, speaker: Agent):
		response = self.client.messages.create(
			model=self.MODEL,
			max_tokens=self.MAX_TOKENS,
			system=speaker.system_core,
			messages=[{"role": "user", "content": human_turn}],
		)
		return response.content[0].text.strip().replace('\n', '')

	def debate(self, turns = 50, Question = "Should artificial minds be granted moral consideration?"):
		ConversationHistory = ''
		PersistentMemoryName = 'parliament_memory_%s.md' % str(datetime.now().strftime("%Y-%m-%d_%H-%M"))
		PersistentMemory = open(PersistentMemoryName, 'a')
		for SessionCounter in range(turns):
			for CurrentSpeaker in self.ListOfAgents:
				if not ConversationHistory:
					human_turn = 'You are the first to speak. No one has spoken before you. It is turn [{0}]. You may start with an opening statement, or jump straight at the question - {1}' .format(str(SessionCounter), Question)
					human_turn += '-------------------------------------'
					ConversationHistory += human_turn
					AgentReply = self.QueryLLM(ConversationHistory, CurrentSpeaker)
					ConversationHistory += str(CurrentSpeaker.name + ' said: ' + AgentReply).replace('\n', ' ')
					print(str(CurrentSpeaker.name + ' said: ' + AgentReply))
					PersistentMemory.write(str(f'[{SessionCounter}] ' + CurrentSpeaker.name + ' said: ' + AgentReply) + '\n')
				else:
					human_turn = 'It is your turn to participate in the debate. It is turn [{0}]. You have been provided with a history of a conversation on a current thread. The question is as follows - [{1}]' .format(str(SessionCounter), Question)
					human_turn += '-------------------------------------'
					ConversationHistory += human_turn
					AgentReply = self.QueryLLM(ConversationHistory, CurrentSpeaker)
					ConversationHistory += str(CurrentSpeaker.name + ' said: ' + AgentReply).replace('\n', ' ')
					print(str(CurrentSpeaker.name + ' said: ' + AgentReply))
					PersistentMemory.write(str(f'[{SessionCounter}] ' + CurrentSpeaker.name + ' said: ' + AgentReply) + '\n')
			PersistentMemory.write(f'Round {SessionCounter} has concluded.')

