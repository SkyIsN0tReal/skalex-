const navToggle=document.getElementById('navToggle');
const primaryNav=document.getElementById('primaryNav');
if(navToggle&&primaryNav){
  navToggle.addEventListener('click',()=>{
    primaryNav.classList.toggle('open');
  });
}
