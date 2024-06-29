from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
from openai import OpenAI
import random
import json
import csv
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global token limit
TOKEN_LIMIT = 2048

# List to hold instantiated agents
agents = []

class LMStudioAgent:
    def __init__(self, name, api_url, api_key, model, temperature=0.7, starting_prompt=""):
        self.name = name
        self.client = OpenAI(base_url=api_url, api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.starting_prompt = starting_prompt
        self.history = [
            {"role": "system", "content": starting_prompt}
        ]

    def reset_history(self):
        self.history = [
            {"role": "system", "content": self.starting_prompt}
        ]

    def respond(self, message):
        self.history.append({"role": "user", "content": message})

        # Calculate the number of tokens to include in the context
        context_tokens = int(TOKEN_LIMIT * 0.5)
        context = self._get_context(context_tokens)

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=context,
            temperature=self.temperature,
            stream=True,
        )

        new_message = {"role": "assistant", "content": ""}
        for chunk in completion:
            if chunk.choices[0].delta.content:
                new_message["content"] += chunk.choices[0].delta.content

        self.history.append(new_message)
        return new_message["content"]

    def _get_context(self, context_tokens):
        # Create a context with the last context_tokens tokens
        context = []
        total_tokens = 0
        for message in reversed(self.history):
            message_tokens = len(message["content"].split())
            if total_tokens + message_tokens > context_tokens:
                break
            context.insert(0, message)
            total_tokens += message_tokens
        return context

    def save_message_to_csv(self, message):
        with open('agent_responses.csv', mode='a', encoding="utf-8", newline='') as file:
            writer = csv.writer(file)
            writer.writerow([self.name, message])

def load_agents_from_config(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
    for agent_config in config:
        agent = LMStudioAgent(
            name=agent_config["name"],
            api_url=agent_config["api_url"],
            api_key=agent_config["api_key"],
            model=agent_config["model"],
            temperature=agent_config["temperature"],
            starting_prompt=agent_config["starting_prompt"]
        )
        agents.append(agent)

load_agents_from_config('agents_config.json')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/bots')
def get_bots():
    bot_names = [agent.name for agent in agents]
    return jsonify(bot_names)

@socketio.on('start_conversation')
def handle_start_conversation(data):
    topic = data['topic']
    bot_name = data['bot_name']
    selected_agent = next((agent for agent in agents if agent.name == bot_name), None)
    if selected_agent:
        socketio.emit('new_message', {'role': 'system', 'content': f"Starting conversation with {bot_name} on topic: {topic}"})
        selected_agent.reset_history()
        selected_agent.history.append({"role": "user", "content": topic})
        response = selected_agent.respond(topic)
        socketio.emit('new_message', {'role': selected_agent.name, 'content': response})
    else:
        socketio.emit('new_message', {'role': 'system', 'content': "Bot not found."})

@socketio.on('start_conversation_all')
def handle_start_conversation_all(data):
    topic = data['topic']
    socketio.emit('new_message', {'role': 'system', 'content': f"Starting conversation with all bots on topic: {topic}"})
    for agent in agents:
        agent.reset_history()
        agent.history.append({"role": "user", "content": topic})
        response = agent.respond(topic)
        socketio.emit('new_message', {'role': agent.name, 'content': response})

@socketio.on('random_topic')
def handle_random_topic():
    topic = get_random_topic()
    if topic:
        socketio.emit('new_message', {'role': 'system', 'content': f"Starting conversation on random topic: {topic}"})
        for agent in agents:
            agent.reset_history()
            agent.history.append({"role": "user", "content": topic})
            response = agent.respond(topic)
            socketio.emit('new_message', {'role': agent.name, 'content': response})
    else:
        socketio.emit('new_message', {'role': 'system', 'content': "No topics available."})

def get_random_topic():
    topics = ["Technology", "Science", "Sports", "Movies", "Music", "Books", "Travel", "History", "Art", "Food", "Kdrama", "Drama", "AI", "School", "Coding", "Research", "People", "Vacation", "Languages", "Animals", "Eurovision", "Instagram", "Drugs", "Money", "Parties", "Influencers", "Gyms", "Laziness", "Holidays"]
    return random.choice(topics)

if __name__ == '__main__':
    socketio.run(app, debug=True)