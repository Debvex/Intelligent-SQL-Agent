#!/bin/bash
# Pull llama3.2:3b on first Docker start
ollama serve &
sleep 5
ollama pull llama3.2:3b
wait