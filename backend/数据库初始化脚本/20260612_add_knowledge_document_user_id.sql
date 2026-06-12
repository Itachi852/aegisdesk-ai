USE aegisdeskai;

ALTER TABLE knowledge_documents
  ADD COLUMN user_id BIGINT NULL AFTER id;

UPDATE knowledge_documents
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE knowledge_documents
  MODIFY COLUMN user_id BIGINT NOT NULL;

CREATE INDEX idx_knowledge_documents_user_id
  ON knowledge_documents(user_id);
