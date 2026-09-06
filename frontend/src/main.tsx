import React from 'react'
import ReactDOM from 'react-dom/client'
import '@quorum/ui/styles/tokens.css'
// Side-effecting: registers this corpus's nouns with the platform components.
import './strings'
import { App } from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
