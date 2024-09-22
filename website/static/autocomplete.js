window.addedTags = new Set();
window.addedIngredients = new Set();

let addedTags = window.addedTags;
let addedIngredients = window.addedIngredients;

function autocomplete(inp, tags_inp, ingredients_inp) {
  var currentFocus;
  inp.addEventListener("input", function(e) {
    var a, b, i, val = this.value;
    closeAllLists();
    if (!val) { return false;}
    currentFocus = -1;
    a = document.createElement("DIV");
    a.setAttribute("id", this.id + "autocomplete-list");
    a.setAttribute("class", "autocomplete-items");
    this.parentNode.appendChild(a);
    
    function addSuggestion(item, type) {
      b = document.createElement("DIV");
      b.innerHTML = type + ": ";
      b.innerHTML += "<strong>" + item.substr(0, val.length) + "</strong>";
      b.innerHTML += item.substr(val.length);
      b.innerHTML += "<input type='hidden' value='" + item + "'>";
      b.addEventListener("click", function(e) {
        const selectedValue = this.getElementsByTagName("input")[0].value;
        if (addItemComponent(selectedValue, type, inp)) {
          inp.value = "";
          closeAllLists();
          inp.focus(); // Add this line to set focus back to the input
        }
      });
      a.appendChild(b);
    }

    if (tags_inp) {
      for (const key in tags_inp) {
        if (tags_inp[key].name.substr(0, val.length).toUpperCase() == val.toUpperCase()) {
          addSuggestion(tags_inp[key].name, "Tag");
        }
      }
    }

    if (ingredients_inp) {
      for (const key in ingredients_inp) {
        if (ingredients_inp[key].name.substr(0, val.length).toUpperCase() == val.toUpperCase()) {
          addSuggestion(ingredients_inp[key].name, "Ingredient");
        }
      }
    }
  });

  inp.addEventListener("keydown", function(e) {
    var x = document.getElementById(this.id + "autocomplete-list");
    if (x) x = x.getElementsByTagName("div");
    if (e.keyCode == 40) {
      currentFocus++;
      addActive(x);
    } else if (e.keyCode == 38) {
      currentFocus--;
      addActive(x);
    } else if (e.keyCode == 13) {
      e.preventDefault();
      if (currentFocus > -1) {
        if (x) x[currentFocus].click();
      }
    }
  });

  function addActive(x) {
    if (!x) return false;
    removeActive(x);
    if (currentFocus >= x.length) currentFocus = 0;
    if (currentFocus < 0) currentFocus = (x.length - 1);
    x[currentFocus].classList.add("autocomplete-active");
  }

  function removeActive(x) {
    for (var i = 0; i < x.length; i++) {
      x[i].classList.remove("autocomplete-active");
    }
  }

  function closeAllLists(elmnt) {
    var x = document.getElementsByClassName("autocomplete-items");
    for (var i = 0; i < x.length; i++) {
      if (elmnt != x[i] && elmnt != inp) {
        x[i].parentNode.removeChild(x[i]);
      }
    }
  }

  document.addEventListener("click", function (e) {
    closeAllLists(e.target);
  });
}

function addItemComponent(value, type, inputElement) {
  const itemSet = type === "Tag" ? addedTags : addedIngredients;
  
  if (itemSet.has(value)) {
    alert(`This ${type.toLowerCase()} has already been added.`);
    return false;  // Return false to indicate the item was not added
  }

  itemSet.add(value);

  const itemContainer = document.createElement("div");
  itemContainer.className = "item-component";
  itemContainer.setAttribute('data-type', type);
  itemContainer.innerHTML = `
    <span>${type}: ${value}</span>
    <button class="remove-item">×</button>
  `;
  
  itemContainer.querySelector('.remove-item').addEventListener('click', function() {
    itemContainer.remove();
    itemSet.delete(value);
  });

  // Insert the new item component after the input field
  inputElement.parentNode.insertBefore(itemContainer, inputElement.nextSibling);
  return true;  // Return true to indicate the item was successfully added
}