import React from "react";
import ReactDOM from "react-dom/client";
import "./style.css";

function App() {
  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold text-blue-600">Hello from Jev</h1>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);