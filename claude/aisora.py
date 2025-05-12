# This script is designed to run indefinitely, listening for incoming messages and responding as needed.
import subprocess
import json
import time
import os
import signal
import psutil
import anthropic
import uuid
import re
from config import ANTHROPIC_API_KEY, SIGNAL_NUMBER, SYSTEM_PROMPT, AI_ASSISTANT_NICKNAME, MODEL_CONFIG
from db_utils import log_conversation, get_recent_conversation_history, get_db_connection
from psycopg2.extras import RealDictCursor
from location_utils import get_location_from_phone_number, clear_location_cache
from attachment_helper import get_attachment, process_image_file, extract_attachment_id_from_signal_response

# Set an environment variable to enable IP-based location fallback.
os.environ['ALLOW_IP_FALLBACK'] = 'true'

# Connect to Claude.
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def format_response(text):
    # Replace various bullet styles with a unified bullet style.
    text = text.replace('- ', '• ').replace('* ', '• ')
    
    # Split text into lines, and then process it.
    lines = text.split('\n')
    formatted = []
    last_was_bullet = False
    in_bullet_list = False
    last_was_empty = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        is_bullet = line.startswith('• ')
        is_empty = len(line) == 0
        
        # Handle bullet points.
        if is_bullet:
            if not in_bullet_list:
                # Add blank lines before the first bullet in a list.
                formatted.append('')
                formatted.append('')
                in_bullet_list = True
            formatted.append(line) # Add a bullet point.
            last_was_bullet = True
            last_was_empty = False
        # Handle paragraph transitions.
        elif not is_empty and i > 0 and not last_was_empty and not last_was_bullet:
            # This is a new paragraph (not after a bullet or empty line).
            # Add a double line break before a new paragraph.
            formatted.append('')
            formatted.append('')
            formatted.append(line)
            last_was_bullet = False
            last_was_empty = False
            in_bullet_list = False
        # Handle the end of a bulleted list.
        elif last_was_bullet and not is_empty:
            # Transition from bullets to text.
            formatted.append('')
            formatted.append('')
            formatted.append(line)
            last_was_bullet = False
            last_was_empty = False
            in_bullet_list = False
        # Handle regular content.
        elif not is_empty:
            formatted.append(line)
            last_was_bullet = False
            last_was_empty = False
        # Track empty lines.
        else:
            last_was_empty = True
            # Only add one empty line to avoid excessive spacing.
            if not (i > 0 and not formatted[-1]):
                formatted.append('')
    
    result = '\n'.join(formatted)
    
    # Ensure each bullet starts on a new line.
    result = result.replace(' • ', '\n• ')
    
    # Clean up any instances of more than two consecutive newlines.
    while '\n\n\n' in result:
        result = result.replace('\n\n\n', '\n\n')
    
    return result

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

def split_message(message, max_length=500):
    if len(message) <= max_length:
        return [message]
    
    parts = []
    current_part = ""
    
    # Split on paragraphs first to preserve structure.
    paragraphs = message.split('\n\n')
    
    for paragraph in paragraphs:
        # If adding this paragraph exceeds max length and there's already content, then break it onto a new paragraph.
        if current_part and len(current_part) + len(paragraph) + 2 > max_length:
            parts.append(current_part)
            current_part = paragraph
        elif current_part:
            current_part += '\n\n' + paragraph
        else:
            current_part = paragraph
    
    if current_part:
        parts.append(current_part)
    
    # Add part numbers to indicate responses length.
    return [f"{part}\n[{i+1}/{len(parts)}]" for i, part in enumerate(parts)]

def send_signal_message(to_number, message, proc, group_id=None):
    if not message.strip():
        print("Error: Empty message, not sending.")
        return
    
    try:
        # Split the message if needed.
        message_parts = split_message(message)
        
        for part in message_parts:
            json_request = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": {
                    "message": part
                },
                "id": int(time.time())
            }
            
            # Set the recipient differently based on whether this is a group message.
            if group_id:
                json_request["params"]["groupId"] = group_id
            else:
                json_request["params"]["recipient"] = [to_number]
            
            json_str = json.dumps(json_request) + "\n"
            proc.stdin.write(json_str)
            proc.stdin.flush()
            print(f"Sent message part {' to group ' + group_id if group_id else ' to ' + to_number} via JSON-RPC")
            if len(message_parts) > 1:
                time.sleep(3)
    except Exception as e:
        print(f"Failed to send message via JSON-RPC: {e}")

def format_conversation_history(history):
    formatted = []
    for entry in history:
        formatted.extend([
            {"role": "user", "content": entry['query']},
            {"role": "assistant", "content": entry['response']}
        ])
    return formatted

def get_recent_attachment_paths(conversation_id, limit=1):
    """Get the most recent attachment paths from the conversation history."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT attachment_paths 
                FROM query_log 
                WHERE conversation_id = %s AND attachment_paths IS NOT NULL
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (conversation_id, limit))
            results = cur.fetchall()
            
            # Extract and flatten attachments from results.
            attachment_paths = []
            for result in results:
                if result['attachment_paths']:
                    paths = json.loads(result['attachment_paths'])
                    if isinstance(paths, list):
                        attachment_paths.extend(paths)
            
            return attachment_paths

def ask_claude_with_images(question, images=None, conversation_id=None):
    """Send a message to Claude with optional images."""
    print(f"Sending question with images to Claude: {question[:50]}...")
    
    # Start building the message content.
    message_content = []
    
    # Add any images first if provided.
    if images and isinstance(images, list):
        for image_data in images:
            if image_data: # Only add valid image data.
                message_content.append(image_data)
                print("Added image to message content.")
    
    # Check if this is a follow-up query with images from the conversation history.
    is_followup = conversation_id and question.strip() and images 
    
    # For short questions with images, enhance the prompt.
    original_question = question
    if is_followup:
        # For follow-up queries, focus on answering just the question.
        question = f"{question} Please focus only on answering this specific question about the image without describing the image again."
        print(f"Using focused follow-up prompt: {question}")
    elif images and len(question.strip()) < 15 and question.strip():
        question = f"I'm showing you an image and asking: '{question}'. Please analyze what you see in the image and respond accordingly."
        print(f"Enhanced short question prompt: {question}")
    
    # Ensure there's text content, even if empty.
    if not question or not question.strip():
        question = "Please describe this image in detail. Respond directly with your analysis without mentioning that I didn't ask a question."
        print("Using default prompt for empty text message")
    
    # Add the text content.
    message_content.append({"type": "text", "text": question})
    
    messages = [{"role": "user", "content": message_content}]
    
    if conversation_id:
        history = get_recent_conversation_history(conversation_id)
        if history:
            # Filter out any empty history entries.
            valid_history = []
            for entry in history:
                if entry['query'] and entry['response']: # Make sure both query and response exist.
                    valid_history.append(entry)
            
            # For previous messages, only include the text, not images.
            if valid_history:
                formatted_history = format_conversation_history(valid_history)
                messages = formatted_history + messages
    
    try:
        print(f"Calling Claude API with {len(images) if images else 0} images")
        print(f"Using model: {MODEL_CONFIG['model']}") # Add logging to show which model is used.
        response = claude.messages.create(
            model=MODEL_CONFIG['model'],
            max_tokens=MODEL_CONFIG['max_tokens'],
            temperature=MODEL_CONFIG['temperature'],
            system=SYSTEM_PROMPT,
            messages=messages
        )
        print("Successfully received Claude's response")
        return format_response(response.content[0].text)
    except Exception as e:
        print(f"Error in Claude API call: {e}")
        import traceback
        traceback.print_exc()
        raise e

def ask_claude(question, conversation_id=None): # Check if any recent images need to be included.
    previous_images = []
    if conversation_id:
        # Get the paths to recent attachments.
        recent_attachment_paths = get_recent_attachment_paths(conversation_id, limit=1)
        
        # Process any images found.
        for attachment_path in recent_attachment_paths:
            if os.path.exists(attachment_path):
                # Check if the question is likely about a completely different topic.
                # List of words/phrases that typically indicate a new topic unrelated to an image.
                new_topic_indicators = [
                  # Question starters
                  'what is', 'what are', 'what was', 'what were', 'what does', 'what did',
                  'how do', 'how does', 'how can', 'how could', 'how should', 'how would',
                  'who is', 'who was', 'who are', 'who were',
                  'when is', 'when was', 'when are', 'when will',
                  'where is', 'where are', 'where can',
                  'why is', 'why are', 'why does', 'why did',
                  'can you', 'could you',
                  
                  # Information requests
                  'explain', 'tell me about', 'define', 'describe', 'elaborate on',
                  'history of', 'meaning of', 'purpose of', 'origin of', 'background of',
                  'details about', 'information on', 'overview of', 'summary of',
                  'facts about', 'statistics on', 'data about',
                  
                  # Comparison phrases
                  'versus', 'vs.', 'vs', 'compared to', 'difference between', 'similarities between',
                  'better than', 'worse than', 'pros and cons',
                  
                  # Common topics unrelated to images
                  'weather', 'news', 'latest', 'current', 'recent', 'trending',
                  'recipe', 'recipes', 'how to make', 'how to cook',
                  'stock', 'stocks', 'price', 'prices', 'cost', 'value',
                  'capital of', 'population of', 'located in', 'distance between',
                  
                  # Time-related shifts
                  'today', 'yesterday', 'tomorrow', 'this week', 'last week', 'next week',
                  'schedule', 'time', 'date', 'upcoming', 'event',
                  
                  # Media and entertainment
                  'movie', 'film', 'show', 'series', 'episode', 'book', 'song', 'album', 'artist',
                  'review', 'rating', 'cast', 'plot', 'release date',
                  
                  # Product/service inquiries
                  'how much is', 'how much does', 'price of', 'cost of', 'where to buy',
                  'best', 'recommended', 'top', 'review of', 'features of',
                  
                  # Academic/work
                  'homework', 'assignment', 'project', 'thesis', 'paper', 'research',
                  'formula for', 'equation', 'calculate', 'solve',
                  
                  # Technology
                  'how to install', 'how to set up', 'how to configure', 'how to use',
                  'download', 'update', 'upgrade', 'fix', 'troubleshoot',
                  
                  # Health
                  'symptoms of', 'treatment for', 'cure for', 'causes of', 'prevention of',
                  'diagnosis', 'diet', 'exercise', 'nutrition',
                  
                  # Travel
                  'flights to', 'hotels in', 'visit', 'vacation', 'travel to', 'tourism',
                  
                  # Direct commands/requests
                  'write', 'create', 'generate', 'draft', 'compose', 'make',
                  'help me with', 'assist me', 'guide me', 'advice on',
                  'translate', 'convert', 'change'
              ]
                
                # Check if the question seems like a general knowledge query.
                question_lower = question.lower()
                is_general_knowledge = any(indicator in question_lower for indicator in new_topic_indicators)
                
                # Skip image inclusion for questions that are likely about general knowledge.
                if is_general_knowledge:
                    print(f"Question appears to be about general knowledge, skipping image inclusion")
                else:
                    image_data = process_image_file(attachment_path)
                    if image_data:
                        previous_images.append(image_data)
                        print(f"Including previous image from: {attachment_path} for context")
    
    # If there are any previous images, use the ask_claude_with_images function.
    if previous_images:
        return ask_claude_with_images(question, previous_images, conversation_id)
    
    # Otherwise, proceed with a text-only query.
    # Ensure the question is not empty.
    if not question.strip():
        question = "Hello" # Default message, if empty.
        print("Warning: Empty question detected. Using the default greeting.")
    
    messages = [{"role": "user", "content": question}]
    
    if conversation_id:
        history = get_recent_conversation_history(conversation_id)
        if history:
            valid_history = []
            for entry in history:
                # Validate that both the query and the response exist and are not empty.
                if entry.get('query') and entry.get('query').strip() and entry.get('response') and entry.get('response').strip():
                    valid_history.append(entry)
            
            if valid_history:
                formatted_history = format_conversation_history(valid_history)
                messages = formatted_history + messages
    
    # Final validation - Ensure that no message has empty content.
    messages = [msg for msg in messages if msg.get('content')]
    
    # Ensure that there is at least one message.
    if not messages:
        messages = [{"role": "user", "content": "Hello"}]
        print("Warning: No valid messages found. Using the default greeting.")
    
    response = claude.messages.create(
        model=MODEL_CONFIG['model'],
        max_tokens=MODEL_CONFIG['max_tokens'],
        temperature=MODEL_CONFIG['temperature'],
        system=SYSTEM_PROMPT,
        messages=messages
    )
    return format_response(response.content[0].text)

def listen_for_messages(proc):
    # Keep track of already processed messages to avoid duplicates.
    processed_messages = set()
    
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
            timestamp = envelope.get("timestamp", "")
            
            # Create a unique key for this message to prevent duplication.
            message_data = envelope.get("dataMessage", {})
            message_text = message_data.get("message")
            
            # Fix: Handle None message_text safely.
            safe_message = "" if message_text is None else message_text
            message_key = f"{source}:{timestamp}:{safe_message[:50]}"
            
            # Skip if the message has already been processed.
            if message_key in processed_messages:
                print(f"Skipping already processed message: {message_key}")
                continue
            
            # Add to processed messages.
            processed_messages.add(message_key)
            
            # Limit the size of processed_messages to prevent memory issues.
            if len(processed_messages) > 1000:
                processed_messages = set(list(processed_messages)[-500:])
            
            # Extract the sender's name if available.
            sender_name = None
            if "sourceName" in envelope:
                sender_name = envelope.get("sourceName")
            
            # Check for attachments.
            attachments = message_data.get("attachments", [])
            attachment_ids = [att.get("id") for att in attachments if att.get("contentType", "").startswith("image/")]
            
            # Check if the message is in a group chat.
            is_group = False
            group_id = None
            if "groupInfo" in message_data:
                is_group = True
                group_id = message_data["groupInfo"].get("groupId")
            
            # Check for mentions in the message metadata.
            mentions = message_data.get("mentions", [])
            is_mentioned = False
            for mention in mentions:
                if mention.get("number") == SIGNAL_NUMBER:
                    is_mentioned = True
                    print(f"Bot was officially mentioned in metadata: {mention}")
                    break
            
            # Update condition to handle messages with no text but with attachments.
            if source and (attachment_ids or (message_text is not None and message_text.strip())):
                yield source, "" if message_text is None else message_text, is_group, group_id, is_mentioned, sender_name, attachment_ids

def remove_mention(message):
    """Remove the mention from the message to avoid confusing the AI"""
    nickname = re.escape(AI_ASSISTANT_NICKNAME)
    
    # Look for various encodings of the @ symbol that Signal might use.
    replacements = {
        '￼': '@',
        '\ufffc': '@', 
        '\xef\xbf\xbc': '@',
        '\uFEFF': '@',
        '﹫': '@',
    }
    
    processed_message = message
    for char, replacement in replacements.items():
        processed_message = processed_message.replace(char, replacement)
    
    patterns = [
        rf'@{nickname}',
        rf'@\s*{nickname}',
    ]
    
    result = processed_message
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Clean up extra whitespace.
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result

def check_for_mention(message):
    """Check if the message contains a mention of the AI assistant"""
    if message is None:
        return False
        
    nickname = re.escape(AI_ASSISTANT_NICKNAME)
    
    # Look for various encodings of the @ symbol that Signal might use.
    replacements = {
        '￼': '@',
        '\ufffc': '@',
        '\xef\xbf\xbc': '@',
        '\uFEFF': '@',
        '﹫': '@',
    }
    
    processed_message = message
    for char, replacement in replacements.items():
        processed_message = processed_message.replace(char, replacement)
    
    # Check for direct mentions with @ symbol.
    patterns = [
        rf'@{nickname}',
        rf'@\s*{nickname}',
    ]
    
    for pattern in patterns:
        if re.search(pattern, processed_message, re.IGNORECASE):
            print(f"Found mention using pattern: {pattern}")
            return True
    
    # Also check if the message starts with just the name without @ symbol.
    if re.match(rf'^{nickname}[\s:,]', processed_message, re.IGNORECASE):
        print(f"Found mention at start of message: {processed_message[:20]}...")
        return True
    
    return False

def format_mentions_for_db(message):
    """Format message to replace replacement characters with proper @ symbol for database storage"""
    # Look for various encodings of the @ symbol that Signal might use.
    replacements = {
        '￼': '@',
        '\ufffc': '@', 
        '\xef\xbf\xbc': '@',
        '\uFEFF': '@', 
        '﹫': '@',
    }
    
    processed_message = message
    for char, replacement in replacements.items():
        processed_message = processed_message.replace(char, replacement)
    
    # Ensure the AI_ASSISTANT_NICKNAME is properly captured in mentions.
    nickname = AI_ASSISTANT_NICKNAME
    
    # Look for partial mentions that might be missing the nickname.
    partial_mention_pattern = r'@\s*(?!' + re.escape(nickname) + r')'
    if re.search(partial_mention_pattern, processed_message):
        # If there's an @ without the nickname, make sure to add it.
        processed_message = re.sub(partial_mention_pattern, '@' + nickname + ' ', processed_message)
    
    return processed_message

def main():
    kill_existing_signal_cli()
    proc = start_signal_cli_jsonrpc()
    print("Listening for incoming messages...")

    # Store conversation IDs and processed messages.
    conversations = {}
    last_processed_timestamp = {}
    
    last_cache_clear = time.time()
    cache_clear_interval = 3600  # Clear location cache every hour.

    while True:
        if proc.poll() is not None:
            print("Detected that signal-cli has stopped. Restarting...")
            proc = start_signal_cli_jsonrpc()
            time.sleep(2) # Add a small wait time to ensure signal-cli is ready.

        # Periodically clear the location cache to ensure fresh lookups.
        current_time = time.time()
        if current_time - last_cache_clear > cache_clear_interval:
            clear_location_cache()
            last_cache_clear = current_time
            print("Location cache cleared due to scheduled refresh")

        try:
            for sender, message, is_group, group_id, is_mentioned, sender_name, attachment_ids in listen_for_messages(proc):
                # Create a unique key for this conversation.
                convo_key = group_id if is_group and group_id else sender
                
                # Check if this is a new message (by using timestamp tracking).
                message_timestamp = time.time()
                
                # Skip if a message from this sender has already been processed very recently.
                # This prevents the loop from occurring if there are parsing issues.
                if convo_key in last_processed_timestamp and message_timestamp - last_processed_timestamp[convo_key] < 2:
                    print(f"Skipping too-frequent message from {sender} to prevent looping")
                    continue
                
                # Update the last processed timestamp
                last_processed_timestamp[convo_key] = message_timestamp
                
                print(f"Received from {sender}: {message}")
                
                # Try to extract location from phone number if it starts with a +.
                country = city = possible_carrier = location = None
                if sender and isinstance(sender, str) and sender.startswith('+'):
                    # Force a refresh on each message to ensure that the latest data is available.
                    location_info = get_location_from_phone_number(sender, force_refresh=True)
                    if location_info:
                        country = location_info.get('country')
                        city = location_info.get('city')
                        possible_carrier = location_info.get('possible_carrier')
                        location = location_info.get('location')
                        print(f"Extracted location from phone number: {country}, {city}, {possible_carrier}, {location}")
                
                # Only respond if it's a direct message OR if it's a group message that mentions the assistant.
                # First check official mentions from the metadata, then fall back to text-based detection.
                should_respond = not is_group or (is_group and (is_mentioned or check_for_mention(message)))
                
                if should_respond:
                    # Create or get conversation ID for this sender or group.
                    if convo_key not in conversations:
                        conversations[convo_key] = str(uuid.uuid4())

                    # Remove the mention from the message if it's a group message.
                    processed_message = remove_mention(message) if is_group else message
                    
                    # Process attachments if any.
                    images = []
                    attachment_paths = []
                    attachment_error = False
                    
                    for attachment_id in attachment_ids:
                        try:
                            attachment_path = get_attachment(attachment_id, proc)
                            if attachment_path:
                                attachment_paths.append(attachment_path)
                                image_data = process_image_file(attachment_path)
                                if image_data:
                                    images.append(image_data)
                                    print(f"Successfully processed image attachment")
                                else:
                                    print(f"Failed to process image from {attachment_path}")
                                    attachment_error = True
                            else:
                                print(f"Failed to download attachment ID: {attachment_id}")
                                attachment_error = True
                        except Exception as img_err:
                            print(f"Error handling attachment: {img_err}")
                            attachment_error = True
                    
                    # Verify if the message has content (text or images).
                    has_content = processed_message.strip() or (images and len(images) > 0)
                    if not has_content:
                        print("No valid content in message, skipping response")
                        continue
                    
                    try:
                        if images:
                            print(f"Sending message with {len(images)} images to Claude")
                            answer = ask_claude_with_images(processed_message, images, conversations[convo_key])
                        else:
                            answer = ask_claude(processed_message, conversations[convo_key])
                        
                        print(f"Claude's answer: {answer}")
                        
                        # Log the conversation with all location data available.
                        formatted_message = format_mentions_for_db(message)
                        log_conversation(
                            sender, 
                            formatted_message, 
                            answer, 
                            conversations[convo_key], 
                            is_group, 
                            group_id, 
                            sender_name,
                            country,
                            city,
                            possible_carrier,
                            location,
                            attachment_paths # Save attachment paths to the database.
                        )
                        
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                if is_group and group_id:
                                    # For group messages, send to the group and mention the original sender.
                                    send_signal_message(sender, answer, proc, group_id)
                                    print(f"Successfully sent group message to group ID {group_id} with mention to {sender} (attempt {attempt + 1})")
                                else:
                                    # For direct messages, use the sender's number.
                                    send_signal_message(sender, answer, proc)
                                    print(f"Successfully sent direct message to {sender} (attempt {attempt + 1})")
                                break
                            except Exception as send_error:
                                print(f"Failed to send message (attempt {attempt + 1}): {send_error}")
                                if attempt == max_retries - 1:
                                    print("Maximum retries reached, message may not have been sent")
                                time.sleep(2)
                    except Exception as e:
                        print(f"Error getting Claude's response: {e}")
                        import traceback
                        traceback.print_exc()
                        answer = "Sorry, there was an error processing your request."
                        if is_group and group_id:
                            send_signal_message(sender, answer, proc, group_id)
                        else:
                            send_signal_message(sender, answer, proc)
                        time.sleep(1)
                else:
                    print("Message not addressed to assistant, ignoring.")

        except Exception as e:
            print(f"Main loop error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)
            kill_existing_signal_cli()
            proc = start_signal_cli_jsonrpc()
            time.sleep(2)

if __name__ == "__main__":
    main()
