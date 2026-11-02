import axios from 'axios';
export class Api { get(id: string) { return axios.get(`/items/${id}`); } }
export function post() { return fetch('/x', { method: 'POST' }); }
