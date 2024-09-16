function deleteNote(noteId) {
  fetch("/delete-note", {
    method: "POST",
    body: JSON.stringify({ noteId: noteId }),
  }).then((_res) => {
    window.location.href = "/";
  });
}
function deleteRecipe(recipe_id) {
  fetch("/delete-note", {
    method: "POST",
    body: JSON.stringify({ recipe: recipe_id }),
  }).then((_res) => {
    window.location.href = "/profile";
  });
}

