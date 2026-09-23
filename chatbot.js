// Dynamic Backend-Connected Advisory Chatbot Script

async function sendChatMessage() {
    const input = document.getElementById('userInput');
    const chatLog = document.getElementById('chatMessages');
    const query = input.value.trim();

    if (!query) return;

    // 1. Display user message in chat log
    chatLog.innerHTML += `<div class="bg-indigo-50 text-indigo-950 p-3 rounded-lg max-w-lg ml-auto font-medium">${query}</div>`;
    input.value = "";
    chatLog.scrollTop = chatLog.scrollHeight;

    // 2. Add temporary loading/processing indicator
    const loadingId = "loading-" + Date.now();
    chatLog.innerHTML += `<div id="${loadingId}" class="bg-slate-100 p-3 rounded-lg text-slate-500 max-w-lg italic">Analyzing request through backend advisory engine...</div>`;
    chatLog.scrollTop = chatLog.scrollHeight;

    try {
        // 3. Smart detection: check if the query contains a student ID (e.g., numbers like 1002)
        let studentId = null;
        const numberMatch = query.match(/\b(10[0-1][0-5])\b/); // Matches student IDs 1001-1015
        if (numberMatch) {
            studentId = parseInt(numberMatch[1]);
        } else if (!isNaN(query) && query.length >= 3) {
            studentId = parseInt(query);
        }

        // Construct payload expected by FastAPI ChatRequest schema
        const payload = {
            message: query
        };
        if (studentId) {
            payload.student_id = studentId;
        }

        // 4. Send request to FastAPI backend
        const response = await fetch("http://127.0.0.1:8000/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "accept": "application/json"
            },
            body: JSON.stringify(payload)
        });

        // Remove loading indicator
        document.getElementById(loadingId).remove();

        if (!response.ok) {
            throw new Error(`Server returned status ${response.status}`);
        }

        const data = await response.json();

        // 5. Format backend response markdown/text into clean HTML for display
        const formattedResponse = data.response
            .replace(/\n/g, '<br>')
            .replace(/\* /g, '• ');

        chatLog.innerHTML += `<div class="bg-slate-100 p-3 rounded-lg text-slate-700 max-w-lg leading-relaxed shadow-sm">${formattedResponse}</div>`;

    } catch (error) {
        // Remove loading indicator if error occurs
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();

        chatLog.innerHTML += `<div class="bg-red-50 text-red-700 p-3 rounded-lg max-w-lg">Unable to reach backend advisory system. Make sure Uvicorn is running. (${error.message})</div>`;
    }

    chatLog.scrollTop = chatLog.scrollHeight;
}