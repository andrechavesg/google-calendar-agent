// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', (event) => {

    const messagesDiv = document.getElementById('messages');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const sessionIdSpan = document.getElementById('session-id');
    const resetButton = document.getElementById('reset-button');
    console.log('DOM Loaded. Selected messageInput:', messageInput);
    console.log('DOM Loaded. Selected sendButton:', sendButton);
    let ws;
    let sessionId = localStorage.getItem('chatSessionId') || generateUUID();
    localStorage.setItem('chatSessionId', sessionId);
    sessionIdSpan.textContent = sessionId.substring(0, 8); // Display part of the session ID

    let currentBotMessageDiv = null; // To hold the div being streamed into
    let typingInterval = null; // Interval ID for typing effect

    function generateUUID() { // Public Domain/MIT
        let d = new Date().getTime();//Timestamp
        let d2 = ((typeof performance !== 'undefined') && performance.now && (performance.now()*1000)) || 0;//Time in microseconds since page-load or 0 if unsupported
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            let r = Math.random() * 16;//random number between 0 and 16
            if(d > 0){//Use timestamp until depleted
                r = (d + r)%16 | 0;
                d = Math.floor(d/16);
            } else {//Use microseconds since page-load if supported
                r = (d2 + r)%16 | 0;
                d2 = Math.floor(d2/16);
            }
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsUrl = `${wsProtocol}${window.location.host}/ws/${sessionId}`;

        console.log(`Connecting to WebSocket: ${wsUrl}`);
        ws = new WebSocket(wsUrl);

        ws.onopen = function(event) {
            console.log('WebSocket connection opened');
            const initialMessageDiv = document.getElementById('initial-message');
            const initialMessage = initialMessageDiv ? initialMessageDiv.getAttribute('data-message') : "Connected! How can I help?";
            addMessage(initialMessage, 'bot-message');
            setButtonState(true); // Enable input now
        };

        ws.onmessage = function(event) {
            console.log('Raw message from server:', event.data);
            try {
                const data = JSON.parse(event.data);
                console.log('Parsed message from server:', data);

                if (data.type === 'start') {
                    // Create a new div for the bot's response
                    currentBotMessageDiv = document.createElement('div');
                    currentBotMessageDiv.classList.add('message', 'bot-message', 'streaming'); // Add streaming for loader
                    messagesDiv.appendChild(currentBotMessageDiv);
                    setButtonState(false); 
                } else if (data.type === 'final_answer') {
                    // Received the complete answer, stop loader and type it out
                    if (currentBotMessageDiv) {
                        currentBotMessageDiv.classList.remove('streaming'); // Remove loader
                        typeMessage(currentBotMessageDiv, data.message);
                    } else {
                        // Should not happen if 'start' was received, but handle defensively
                        addMessage(data.message, 'bot-message'); 
                    }
                    // NOTE: Button state is handled by 'end' message
                } else if (data.type === 'end') {
                    // Typing effect manages its own interval clearing.
                    // Simply re-enable input and focus.
                    setButtonState(true); // Re-enable input
                    if(messageInput) messageInput.focus(); 
                } else if (data.type === 'error') {
                     // Stop any ongoing typing effect on error
                    if (typingInterval) {
                        clearInterval(typingInterval);
                        typingInterval = null;
                    }
                     if (currentBotMessageDiv) {
                        currentBotMessageDiv.classList.remove('streaming');
                    }
                    addMessage(`Error: ${data.message}`, 'bot-message-error');
                    currentBotMessageDiv = null; 
                    setButtonState(true); 
                    if(messageInput) messageInput.focus();
                } else if (data.type === 'status') {
                    // Handle status updates (displaying agent thoughts/actions)
                    let statusDiv = document.getElementById('status-message');
                    if (!statusDiv) {
                        statusDiv = document.createElement('div');
                        statusDiv.id = 'status-message';
                        statusDiv.classList.add('message', 'system-message', 'status'); // Add specific class
                        // Insert status message before the current bot message div if it exists
                        if (currentBotMessageDiv) {
                            messagesDiv.insertBefore(statusDiv, currentBotMessageDiv);
                        } else {
                            messagesDiv.appendChild(statusDiv);
                        }
                    } else {
                        // Ensure it's placed correctly if it exists
                         if (currentBotMessageDiv && statusDiv.nextSibling !== currentBotMessageDiv) {
                             messagesDiv.insertBefore(statusDiv, currentBotMessageDiv);
                         }
                    }
                    statusDiv.textContent = data.message;
                    messagesDiv.scrollTop = messagesDiv.scrollHeight;
                }

            } catch (e) {
                 console.error('Error parsing message or handling UI update:', e);
                 // Fallback for non-JSON or unknown structure - display raw data
                 addMessage(event.data, 'system-message'); 
                 setButtonState(true); // Re-enable button in case of parsing error
            }
        };

        ws.onerror = function(event) {
            console.error('WebSocket error:', event);
            if (typingInterval) clearInterval(typingInterval);
            typingInterval = null;
            if (currentBotMessageDiv) currentBotMessageDiv.classList.remove('streaming');
            addMessage('WebSocket connection error...', 'bot-message-error'); 
            setButtonState(false);
            currentBotMessageDiv = null;
        };

        ws.onclose = function(event) {
            console.log('WebSocket connection closed:', event);
            if (typingInterval) clearInterval(typingInterval);
            typingInterval = null;
            if (currentBotMessageDiv) currentBotMessageDiv.classList.remove('streaming');
            addMessage('Connection closed...', 'system-message');
            setButtonState(false);
            currentBotMessageDiv = null;
            setTimeout(connectWebSocket, 5000);
        };
    }

    // Function to simulate typing effect
    function typeMessage(element, message) {
        let index = 0;
        const typingSpeed = 30; // Milliseconds per character
        
        // Clear previous interval if any
        if (typingInterval) {
            clearInterval(typingInterval);
        }

        element.innerHTML = ""; // Clear existing content before typing

        typingInterval = setInterval(() => {
            if (index < message.length) {
                // Handle newlines correctly by appending <br>
                if (message.substring(index).startsWith('\n')) {
                    element.innerHTML += '<br>';
                    index++; // Skip the newline character itself
                } else {
                    element.innerHTML += message.charAt(index);
                    index++;
                }
                messagesDiv.scrollTop = messagesDiv.scrollHeight; // Scroll as text types
            } else {
                clearInterval(typingInterval);
                typingInterval = null;
                // Typing finished - button state is handled by 'end' message
            }
        }, typingSpeed);
    }

    function addMessage(message, type) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', type);
        messageElement.innerHTML = message; // Use innerHTML for potential <br>
        messagesDiv.appendChild(messageElement);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        return messageElement;
    }

    function setButtonState(enabled) {
        console.log(`setButtonState called with enabled: ${enabled}`);
        if (sendButton) {
            console.log(`  - Setting sendButton.disabled to ${!enabled}`);
            sendButton.disabled = !enabled;
        }
        if (messageInput) {
             console.log(`  - Setting messageInput.disabled to ${!enabled}`);
            messageInput.disabled = !enabled;
        }
    }

    function sendMessage() {
        const message = messageInput.value.trim();
        if (message && ws && ws.readyState === WebSocket.OPEN) {
             // Display user message immediately using addMessage
            addMessage(message, 'user-message'); 
            ws.send(message); // Send plain text message to backend
            messageInput.value = '';
            setButtonState(false); // Disable input until response starts streaming
        } else if (!ws || ws.readyState !== WebSocket.OPEN) {
            addMessage('Cannot send message: Not connected to the server.', 'bot-message error');
        } 
        // Removed redundant check for empty message as button state handles it
    }

    // --- Event Listeners ---
    if (messageInput) {
        messageInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter' && !sendButton.disabled) {
                sendMessage();
            }
        });
    }
    if (sendButton) {
         sendButton.addEventListener('click', sendMessage);
    }

    // Reset button functionality
    if (resetButton) {
        resetButton.addEventListener('click', function() {
            if (confirm('Are you sure you want to reset the chat session? This will clear your current chat history.')) {
                // Clear the session ID from local storage
                localStorage.removeItem('chatSessionId');
                // Simple reset: Reload the page
                location.reload();
                // Optionally, you could call a backend endpoint to clear server-side session state if necessary
            }
        });
    }

    // Initial setup
    setButtonState(false); // Keep disabled initially
    connectWebSocket();

}); // End DOMContentLoaded listener



