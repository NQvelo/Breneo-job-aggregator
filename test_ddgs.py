from duckduckgo_search import DDGS
import sys

try:
    with DDGS() as ddgs:
        print("Model: gpt-4o-mini")
        res = ddgs.chat("Summarize this: 'Testing DuckDuckGo AI integration for job descriptions.'", model='gpt-4o-mini')
        print(f"Result: {res}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
