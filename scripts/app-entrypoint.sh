#!/bin/bash
# Poll Ollama readiness then start uvicorn
echo "Waiting for Ollama..."
for i in $(seq 1 12); do
  if curl -s http://127.0.0.1:11434 > /dev/null 2>&1; then
    echo "Ollama is ready!"
    break
  fi
  echo "Attempt $i/12: Ollama not ready, waiting 5s..."
  sleep 5
done
exec uvicorn src.main:app --host 0.0.0.0 --port 8000