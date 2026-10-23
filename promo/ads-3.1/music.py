import sys, wave, numpy as np
ad=int(sys.argv[1]); out=sys.argv[2]
SR=44100; T=14.0; N=int(SR*T); t=np.arange(N)/SR
rng=np.random.default_rng(ad)
bpm=[0,112,118,104,120,110,116,108,122,106,126,114,100][ad % 13]; beat=60/bpm
H=1.9 if ad==10 else 2.6; E=10.9
keys=[0,0,3,5,-2,7,2,-4,5,0,-2,4,-3]; k=keys[ad % 13]
progs=[[0,-3,-7,-5],[0,-5,-3,-7],[0,-4,-7,-2]]; prog=progs[ad%3]
f=lambda semi: 110*2**((semi+k)/12)
mix=np.zeros(N); st=np.zeros((N,2))
def add(sig,at,gain=1.0,pan=0.0):
    i=int(at*SR); j=min(N,i+len(sig)); 
    if i>=N: return
    s=sig[:j-i]*gain; st[i:j,0]+=s*(1-pan); st[i:j,1]+=s*(1+pan)
def env(n,a=.005,d=.2):
    x=np.arange(n)/SR; return np.minimum(1,x/a)*np.exp(-x/d)
# барабаны
kl=int(.35*SR); x=np.arange(kl)/SR; kick=np.sin(2*np.pi*(45*x+ (75/18)*(1-np.exp(-18*x))))*np.exp(-x/.12)
nz=lambda n: rng.uniform(-1,1,n)
for b in np.arange(0,E+.01,beat):
    add(kick,b,.9 if b>=H else .55)
nb=int((E)/beat)
for i in range(nb):
    b=i*beat
    if b>=H and i%2==1:
        c=nz(int(.18*SR)); c=np.diff(c,prepend=0)*env(len(c),.002,.06); add(c,b,.35)
    if b>=H*0.6:
        for off in (beat/2,):
            h=np.diff(nz(int(.05*SR)),prepend=0); h=np.diff(h,prepend=0)*env(len(h),.001,.012); add(h,b+off,.18,pan=.3)
# бас и аккорды по тактам
bar=beat*4
for i in range(int(E/bar)+1):
    b=i*bar; root=prog[i%4]; n=int(bar*SR); x=np.arange(n)/SR
    fr=f(root-12)
    for q in range(8):
        o=q*beat/2; m=int(beat/2*SR*.9); xx=np.arange(m)/SR
        saw=2*((fr*xx)%1)-1; tone=np.sin(2*np.pi*fr*xx)*.7+saw*.25
        if b+o>=H*0.5: add(tone*env(m,.004,.14),b+o,.22)
    for semi in (0,3 if ad%2 else 4,7,12):
        fq=f(root+semi+12); tri=2*np.abs(2*((fq*x)%1)-1)-1
        pad=tri*np.minimum(1,x/.25)*np.minimum(1,(bar-x)/.2)
        add(pad,b,.045,pan=(semi-6)/20)
    # арпеджио после крючка
    if b>=H:
        for q in range(8):
            semi=[0,7,12,15 if ad%2 else 16,12,7,19,12][q]; fq=f(root+semi+12); m=int(.22*SR); xx=np.arange(m)/SR
            pl=np.sin(2*np.pi*fq*xx)*env(m,.002,.09); add(pl,b+q*beat/2,.09,pan=.4 if q%2 else -.4)
# свист перехода и удар финала
w=int(.6*SR); x=np.arange(w)/SR; wh=nz(w); wh=np.convolve(wh,np.ones(8)/8,'same')*(x/.6)**2; add(wh,H-.5,.35)
bl=int(1.6*SR); x=np.arange(bl)/SR
boom=np.sin(2*np.pi*(38*x+30*(1-np.exp(-6*x))/6))*np.exp(-x/.5)+nz(bl)*np.exp(-x/.08)*.3
add(boom,E,.9)
# после удара — только мягкий аккорд
n=int((T-E)*SR); x=np.arange(n)/SR
for semi in (0,7,12,16 if ad%2==0 else 15):
    add(np.sin(2*np.pi*f(semi+12)*x)*np.minimum(1,x/.3)*np.exp(-x/2.2),E+.05,.06)
# сведение
fade=np.ones(N); i0=int((T-.8)*SR); fade[i0:]=np.linspace(1,0,N-i0)
st*=fade[:,None]; st=np.tanh(st*1.3); st/=max(1e-9,np.abs(st).max()); st*=.89
with wave.open(out,'wb') as wv:
    wv.setnchannels(2); wv.setsampwidth(2); wv.setframerate(SR); wv.writeframes((st*32767).astype('<i2').tobytes())
