import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

response = client.messages.create(
    model = 'claude-haiku-4-5-20251001',
    max_tokens=200,
    system='You are an expert claude tutor',
    messages=[
        {
            'role':'user',
            'content':'I am preparing for Claude certified architect'
        }
    ]
)

print(response.content[0].text)