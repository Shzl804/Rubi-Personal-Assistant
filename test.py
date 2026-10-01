from groq import Groq
from dotenv import load_dotenv
load_dotenv()
import os
c = Groq(api_key=os.getenv("GROQ_API_KEY"))
print(c.chat.completions.create(model=os.getenv("MODEL_NAME"), messages=[{'role':'user','content':'Say hi in 5 words'}]).choices[0].message.content)
