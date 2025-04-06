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
                    // Create a new div for the bot's response, but don't add text yet
                    currentBotMessageDiv = document.createElement('div');
                    currentBotMessageDiv.classList.add('message', 'bot-message', 'streaming');
                    messagesDiv.appendChild(currentBotMessageDiv);
                    setButtonState(false); // Disable input while streaming
                } else if (data.type === 'stream' && data.token) {
                    if (currentBotMessageDiv) {
                        // Append the token to the current message div
                        // Replace newline characters with <br> for HTML rendering
                        const formattedToken = data.token.replace(/\n/g, '<br>');
                        currentBotMessageDiv.innerHTML += formattedToken; 
                        messagesDiv.scrollTop = messagesDiv.scrollHeight; // Auto-scroll
                    }
                } else if (data.type === 'end') {
                    if (currentBotMessageDiv) {
                        currentBotMessageDiv.classList.remove('streaming');
                    }
                    currentBotMessageDiv = null; // Reset for the next message
                    setButtonState(true); // Re-enable input
                    messageInput.focus(); // Focus input for next message
                } else if (data.type === 'error') {
                    addMessage(`Error: ${data.message}`, 'bot-message-error');
                    if (currentBotMessageDiv) {
                        currentBotMessageDiv.classList.remove('streaming');
                    }
                    currentBotMessageDiv = null; // Reset if an error occurred mid-stream
                    setButtonState(true); // Re-enable input after error
                     messageInput.focus();
                } else {
                     // Handle other message types or plain text if needed
                    console.warn("Received unexpected message format:", data);
                    // Fallback for non-JSON or unknown structure
                    addMessage(event.data, 'bot-message'); 
                    setButtonState(true);
                }

            } catch (e) {
                // Handle cases where the message is not JSON (e.g., simple acknowledgments if any)
                console.log('Received non-JSON message:', event.data);
                // Decide how to handle plain text - maybe display it directly?
                 // addMessage(event.data, 'system-message'); // Example: display as system message
                 // setButtonState(true); // Re-enable button if it was just an ack
            }
        };

        ws.onerror = function(event) {
            console.error('WebSocket error:', event);
            addMessage('WebSocket connection error. Please try refreshing the page.', 'bot-message-error');
            setButtonState(false);
             currentBotMessageDiv = null;
        };

        ws.onclose = function(event) {
            console.log('WebSocket connection closed:', event);
            addMessage('Connection closed. Attempting to reconnect...', 'system-message');
            setButtonState(false);
            currentBotMessageDiv = null;
            setTimeout(connectWebSocket, 5000);
        };
    }

    function addMessage(message, type) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', type);
        // Use innerHTML to render potential <br> tags from streaming
        messageElement.innerHTML = message; 
        messagesDiv.appendChild(messageElement);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        return messageElement; // Return the created element
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



