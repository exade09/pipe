import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import Docs from "./Docs.jsx";
import "./styles.css";

const path = window.location.pathname.replace(/\/+$/, "") || "/";
const Root = path === "/docs" ? Docs : App;

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Root />
  </StrictMode>
);
