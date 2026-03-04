const counters = document.querySelectorAll(".counter");

counters.forEach(counter=>{
  let start=0;
  const target=+counter.dataset.target;

  const update=()=>{
    if(start<target){
      start++;
      counter.innerText=start;
      setTimeout(update,20);
    }else{
      counter.innerText=target;
    }
  };
  update();
});
