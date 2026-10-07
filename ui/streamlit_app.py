import base64
import os

import httpx
import streamlit as st


API_URL = os.getenv("RUBI_API_URL", "http://127.0.0.1:8000").rstrip("/")


def api_call(method, path, **kwargs):
    try:
        response = httpx.request(
            method, API_URL + path, timeout=180.0, **kwargs
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as error:
        detail = error.response.text
        st.error("Rubi API error: {}".format(detail))
    except httpx.HTTPError as error:
        st.error(
            "Cannot reach the FastAPI server at {}. Start it with uvicorn first. ({})".format(
                API_URL, error
            )
        )
    return None


st.set_page_config(page_title="Rubi Assistant", page_icon="🤖", layout="wide")
st.title("Rubi Assistant")
st.caption("Streamlit UI backed by FastAPI")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.subheader("Connection")
    health = api_call("GET", "/health")
    if health:
        st.success("API online")
        st.caption("Profile: {}".format(health.get("model_profile", "default")))

    st.subheader("Controls")
    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        api_call("POST", "/command", json={"message": "/clear"})
        st.rerun()

    command = st.text_input("Run a Rubi command", placeholder="/memory list")
    if st.button("Run command", use_container_width=True) and command:
        result = api_call("POST", "/command", json={"message": command})
        if result:
            st.info(result["reply"])

    st.subheader("Voice conversation")
    voice_file = st.audio_input("Record a message")
    send_voice = st.button("Send voice message", use_container_width=True)
    if voice_file is not None and send_voice:
        result = api_call(
            "POST",
            "/voice",
            files={
                "audio": (
                    voice_file.name or "voice.wav",
                    voice_file.getvalue(),
                    voice_file.type or "audio/wav",
                )
            },
        )
        if result:
            transcript = result.get("transcript", "")
            reply = result.get("reply", "")
            if transcript:
                st.session_state.messages.append(
                    {"role": "user", "content": "🎙️ " + transcript}
                )
            st.session_state.messages.append(
                {"role": "assistant", "content": reply}
            )
            st.success("Rubi heard: {}".format(transcript or "(no speech)"))
            if result.get("audio"):
                audio_bytes = base64.b64decode(result["audio"]["base64"])
                st.audio(audio_bytes, format=result["audio"]["mime"])
            elif result.get("audio_error"):
                st.warning("Text reply is ready, but voice synthesis failed: {}".format(
                    result["audio_error"]
                ))

    st.subheader("Memory")
    memory_query = st.text_input("Search memory", placeholder="coding preferences")
    if st.button("Search memory", use_container_width=True) and memory_query:
        result = api_call(
            "POST", "/memory/search", json={"query": memory_query}
        )
        if result:
            memories = result.get("memories", [])
            if memories:
                for memory in memories:
                    st.write("- {}".format(memory["content"]))
            else:
                st.caption("No matching memories.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Talk to Rubi...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Rubi is thinking..."):
            result = api_call("POST", "/chat", json={"message": prompt})
            reply = result["reply"] if result else "I could not reach the Rubi API."
            st.markdown(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
