export async function validateFlight(lat:number, lon:number, alt:number, drone_id:string){
  const r = await fetch('/api/validate', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({lat,lon,alt, drone_id, query:"validate flight DGCA NOTAM"})})
  if(!r.ok) throw new Error(await r.text())
  return r.json() as Promise<{verdict:string, reason:string, citations:string[], ticket_id:string, requires_human:boolean, retrieved:string[]}>
}
export async function health(){ const r=await fetch('/api/health'); return r.json()}
