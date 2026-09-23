// Fallback base URL for local development
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function fetchStudents() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/students/search`, {
      method: "GET",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`HTTP Error Status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("CORS / Network Error in fetchStudents:", error);
    throw error;
  }
}

export async function sendChatMessage(studentId: number | null, message: string) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        student_id: studentId,
        message: message,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP Error Status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("CORS / Network Error in sendChatMessage:", error);
    throw error;
  }
}