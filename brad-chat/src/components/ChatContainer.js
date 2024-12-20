import React, { useRef, useEffect } from 'react';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import "highlight.js/styles/github.css";
import hljs from "highlight.js";

function ChatContainer({ messages, onSendMessage }) {

  // UseEffect to highlight syntax when messages change
  useEffect(() => {
    hljs.highlightAll();

    var messageList = document.getElementById("message-list");
    if (messageList){
      console.log("yes message list exists")
      messageList.scrollTop = messageList.scrollHeight;
    }
  }, [messages]);

  //<RagFileInput />
  // <ThemeChangeButton />
      

  return (
    <div className="chat-container">
      {/* Display the messages */}
      <MessageList messages={messages} />
      {/* Pass the onSendMessage handler to MessageInput */}
      <MessageInput onSendMessage={onSendMessage} />
    </div>
  );
}

export default ChatContainer;
