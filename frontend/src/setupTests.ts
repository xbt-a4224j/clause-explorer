// Registers this corpus's nouns before any component renders. Without it every shared
// component throws, which is the intended behaviour — it just has to happen once.
import './strings'
import '@testing-library/jest-dom'
