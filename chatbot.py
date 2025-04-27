import subprocess
import json
import time
import os
import signal
import psutil
import anthropic
from config import ANTHROPIC_API_KEY, SIGNAL_NUMBER

# Connect to Claude
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def kill_existing_signal_cli():
    print("Stopping any existing Signal CLI services...")
    for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and "signal-cli" in cmdline:
                print(f"Terminating existing signal-cli process: PID {proc.info['pid']}")
                os.kill(proc.info['pid'], signal.SIGKILL)
                time.sleep(2)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(1)

def start_signal_cli_jsonrpc():
    proc = subprocess.Popen(
        ["signal-cli", "-u", SIGNAL_NUMBER, "jsonRpc"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return proc

def send_signal_message(to_number, message, proc):
    if not message.strip():
        print("Error: Empty message, not sending.")
        return
    
    try:
        # Split message if needed
        message_parts = split_message(message)
        
        for part in message_parts:
            json_request = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": {
                    "recipient": [to_number],
                    "message": part
                },
                "id": int(time.time())
            }
            json_str = json.dumps(json_request) + "\n"
            proc.stdin.write(json_str)
            proc.stdin.flush()
            print(f"Sent message part to {to_number} via JSON-RPC")
            time.sleep(1)  # Add small delay between parts
    except Exception as e:
        print(f"Failed to send message via JSON-RPC: {e}")

def ask_claude(question):
    response = claude.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=8192,
        messages=[
            {"role": "user", "content": question}
        ]
    )
    return response.content[0].text

def listen_for_messages(proc):
    while True:
        line = proc.stdout.readline()
        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("jsonrpc") == "2.0" and data.get("method") == "receive":
            params = data.get("params", {})
            envelope = params.get("envelope", {})
            source = envelope.get("source")
            message_data = envelope.get("dataMessage", {})
            message_text = message_data.get("message")

            if source and message_text:
                yield source, message_text

def main():
    kill_existing_signal_cli()
    proc = start_signal_cli_jsonrpc()
    print("Listening for incoming messages...")

    while True:
        if proc.poll() is not None:
            print("Detected that signal-cli has stopped. Restarting...")
            proc = start_signal_cli_jsonrpc()
            time.sleep(2)  # small wait to ensure it's ready

        try:
            for sender, message in listen_for_messages(proc):
                print(f"Received from {sender}: {message}")

                try:
                    answer = ask_claude(message)
                    print(f"Claude's answer: {answer}")
                    
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            send_signal_message(sender, answer, proc)  # Pass proc here
                            print(f"Successfully sent message to {sender} (attempt {attempt + 1})")
                            break
                        except Exception as send_error:
                            print(f"Failed to send message (attempt {attempt + 1}): {send_error}")
                            if attempt == max_retries - 1:
                                print("Maximum retries reached, message may not have been sent")
                            time.sleep(2)
                except Exception as e:
                        print(f"Error getting Claude's response: {e}")
                        answer = "Sorry, there was an error processing your request."
                        send_signal_message(sender, answer, proc)
                        time.sleep(1)

        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(5)
            kill_existing_signal_cli()
            proc = start_signal_cli_jsonrpc()
            time.sleep(2)

if __name__ == "__main__":
    main()
