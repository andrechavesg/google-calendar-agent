// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', (event) => {

    const messagesDiv = document.getElementById('messages');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.querySelector('#input-area button');
    const sessionIdSpan = document.getElementById('session-id');
    console.log('DOM Loaded. Selected messageInput:', messageInput);
    console.log('DOM Loaded. Selected sendButton:', sendButton);
    let ws;
    let sessionId = localStorage.getItem('chatSessionId') || generateUUID();
    localStorage.setItem('chatSessionId', sessionId);
    sessionIdSpan.textContent = sessionId.substring(0, 8); // Display part of the session ID

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
            console.log('ws.onopen - messageInput:', messageInput);
            console.log('ws.onopen - sendButton:', sendButton);
            const initialMessageDiv = document.getElementById('initial-message');
            const initialMessage = initialMessageDiv ? initialMessageDiv.getAttribute('data-message') : "Connected! How can I help?";
            addMessage(initialMessage, 'bot-message');
            // Use the already selected element
            if (messageInput) messageInput.disabled = false;
            if (sendButton) sendButton.disabled = false;
        };

        ws.onmessage = function(event) {
            console.log('Message from server:', event.data);
            if (event.data !== "Processing your request...") {
                addMessage(event.data, 'bot-message');
            }
            setButtonState(true);
        };

        ws.onerror = function(event) {
            console.error('WebSocket error:', event);
            addMessage('WebSocket connection error. Please try refreshing the page.', 'bot-message error');
            setButtonState(false);
        };

        ws.onclose = function(event) {
            console.log('WebSocket connection closed:', event);
            addMessage('Connection closed.', 'system-message');
            setButtonState(false);
            setTimeout(connectWebSocket, 5000);
        };
    }

    function addMessage(message, type) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', type);
        messageElement.appendChild(document.createTextNode(message));
        messagesDiv.appendChild(messageElement);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function setButtonState(enabled) {
        if (sendButton) sendButton.disabled = !enabled;
        if (messageInput) messageInput.disabled = !enabled;
    }

    function sendMessage() {
        const message = messageInput.value.trim();
        if (message && ws && ws.readyState === WebSocket.OPEN) {
            addMessage(message, 'user-message');
            ws.send(message);
            messageInput.value = '';
            setButtonState(false);
        } else if (!ws || ws.readyState !== WebSocket.OPEN) {
            addMessage('Cannot send message: Not connected to the server.', 'bot-message error');
        } else if (!message) {
            addMessage('Please type a message first.', 'bot-message error');
        }
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

    // Initial setup
    setButtonState(false); // Disable button until connected
    connectWebSocket();

}); // End DOMContentLoaded listener



