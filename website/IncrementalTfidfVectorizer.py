from scipy.sparse import vstack, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from collections import Counter
import numpy as np

class IncrementalTfidfVectorizer:
    def __init__(self, initial_vectorizer=None):
        self.vectorizer = initial_vectorizer or TfidfVectorizer()
        self.vocabulary_ = self.vectorizer.vocabulary_ if initial_vectorizer else {}
        self.idf_ = self.vectorizer.idf_ if initial_vectorizer else None
        self.document_count = 0
        self.term_doc_freq = Counter()
        self.doc_term_matrix = csr_matrix((0, len(self.vocabulary_)))
        self.doc_lengths = []

    def partial_fit(self, X):
        if not isinstance(X, list):
            X = [X]
        
        new_terms = set()
        new_doc_vectors = []
        for doc in X:
            terms = self.vectorizer.build_analyzer()(doc)
            new_terms.update(terms)
            doc_terms = Counter(terms)
            self.term_doc_freq.update(doc_terms)
            self.document_count += 1
            new_doc_vectors.append(doc_terms)
            self.doc_lengths.append(sum(doc_terms.values()))

        # Update vocabulary efficiently
        new_vocab_terms = new_terms - set(self.vocabulary_)
        self.vocabulary_.update({term: idx for idx, term in enumerate(new_vocab_terms, start=len(self.vocabulary_))})

        # Update document-term matrix
        new_matrix = self._vectors_to_matrix(new_doc_vectors)
        
        # Ensure new_matrix has the same number of columns as doc_term_matrix
        if self.doc_term_matrix.shape[1] < new_matrix.shape[1]:
            # Expand doc_term_matrix
            expanded_matrix = csr_matrix((self.doc_term_matrix.shape[0], new_matrix.shape[1]))
            expanded_matrix[:, :self.doc_term_matrix.shape[1]] = self.doc_term_matrix
            self.doc_term_matrix = expanded_matrix
        elif self.doc_term_matrix.shape[1] > new_matrix.shape[1]:
            # Expand new_matrix
            expanded_new_matrix = csr_matrix((new_matrix.shape[0], self.doc_term_matrix.shape[1]))
            expanded_new_matrix[:, :new_matrix.shape[1]] = new_matrix
            new_matrix = expanded_new_matrix

        self.doc_term_matrix = vstack([self.doc_term_matrix, new_matrix])

        # Update IDF
        self._update_idf()

    def remove_document(self, doc_index):
        if doc_index < 0 or doc_index >= self.doc_term_matrix.shape[0]:
            raise ValueError("Invalid document index")

        # Remove the document from the matrix
        doc_vector = self.doc_term_matrix[doc_index]
        self.doc_term_matrix = vstack([self.doc_term_matrix[:doc_index], self.doc_term_matrix[doc_index+1:]])

        # Update term frequencies and document count
        doc_terms = doc_vector.nonzero()[1]
        for term_idx in doc_terms:
            term = list(self.vocabulary_.keys())[list(self.vocabulary_.values()).index(term_idx)]
            self.term_doc_freq[term] -= 1
            if self.term_doc_freq[term] == 0:
                del self.term_doc_freq[term]

        self.document_count -= 1
        del self.doc_lengths[doc_index]

        # Update IDF
        self._update_idf()

    def transform(self, X):
        if not isinstance(X, list):
            X = [X]
        
        doc_vectors = []
        for doc in X:
            terms = self.vectorizer.build_analyzer()(doc)
            vec = Counter(terms)
            doc_vectors.append(vec)

        matrix = self._vectors_to_matrix(doc_vectors)
        return self._apply_tfidf(matrix)

    def _update_idf(self):
        self.idf_ = np.log((self.document_count + 1) / (np.array(list(self.term_doc_freq.values())) + 1)) + 1
        self.vectorizer.idf_ = self.idf_

    def _vectors_to_matrix(self, vectors):
        rows, cols, data = [], [], []
        for i, vec in enumerate(vectors):
            for term, count in vec.items():
                if term in self.vocabulary_:
                    rows.append(i)
                    cols.append(self.vocabulary_[term])
                    data.append(count)
        return csr_matrix((data, (rows, cols)), shape=(len(vectors), len(self.vocabulary_)))

    def _apply_tfidf(self, matrix):
        # Apply IDF
        idf = self.idf_[matrix.indices]
        matrix.data = matrix.data.astype(float) * idf

        # Normalize by document length
        row_sums = np.array(matrix.sum(axis=1)).flatten()
        row_indices, _ = matrix.nonzero()
        matrix.data /= row_sums[row_indices]

        return matrix
