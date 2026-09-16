from flop_empires.identity import EphemeralSigner,ExternalRefereeSigner
from flop_empires.technocore import RoomEnvelope

class Backend:
    def __init__(self): self.inner=EphemeralSigner(b'x'*32); self._nonce=0
    def status(self): return {'ready':True,'did':self.inner.did}
    def sign(self,message:bytes): return self.inner.sign(message)
    def sign_room(self,room:str,text:str):
        self._nonce+=1; nonce=str(self._nonce)
        sig=self.inner.sign(f'{room}|{nonce}|{text}'.encode())
        return RoomEnvelope(self.inner.did,nonce,sig,text)

def test_external_referee_delegates_verified_room_envelopes():
    backend=Backend(); signer=ExternalRefereeSigner(backend.inner.did,backend)
    envelope=signer.sign_room('room-a','{}')
    assert envelope.did==signer.did and envelope.text=='{}' and envelope.nonce=='1'
