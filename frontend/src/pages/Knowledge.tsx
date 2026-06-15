import { Button, Empty, Modal, Popconfirm, Table, Tag, Tooltip, Upload, message } from "antd";
import type { UploadProps } from "antd";
import { useEffect, useState } from "react";
import {
  deleteKnowledgeDocument,
  listKnowledgeDocuments,
  uploadKnowledgeDocument,
  type KnowledgeDocument
} from "../api/client";

const TEXT = {
  title: "知识库文档",
  upload: "上传文档",
  uploadHint: "支持 .txt / .md",
  uploadSuccess: "文档上传并解析完成",
  uploadFailed: "文档上传失败",
  loadFailed: "知识库加载失败",
  delete: "删除",
  deleteTitle: "删除文档",
  deleteDescription: "确定删除这个知识库文档吗？",
  deleteSuccess: "文档已删除",
  deleteFailed: "文档删除失败",
  duplicateTitle: "已存在相同内容的文档",
  duplicateProcessingTitle: "相同文档正在处理中",
  cancel: "取消",
  empty: "暂无文档",
  name: "文档名称",
  type: "类型",
  status: "状态",
  processing: "处理中",
  ready: "就绪",
  failed: "失败",
  uploadTime: "上传时间",
  action: "操作"
};

function getFileType(fileName: string) {
  const suffix = fileName.split(".").pop();
  return suffix ? suffix.toLowerCase() : "";
}

function renderStatus(status: string, record: KnowledgeDocument) {
  if (status === TEXT.processing) {
    return <Tag color="processing">{TEXT.processing}</Tag>;
  }
  if (status === TEXT.ready) {
    return <Tag color="success">{TEXT.ready}</Tag>;
  }
  if (status === TEXT.failed) {
    const tag = <Tag color="error">{TEXT.failed}</Tag>;
    return record.error_message ? <Tooltip title={record.error_message}>{tag}</Tooltip> : tag;
  }
  return status;
}

async function calculateFileHash(file: File) {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function findDuplicateDocument(documents: KnowledgeDocument[], file: File, fileHash?: string) {
  const fileType = getFileType(file.name);
  return documents.find((item) => {
    if (![TEXT.ready, TEXT.processing].includes(item.status)) {
      return false;
    }
    if (fileHash && item.file_hash === fileHash) {
      return true;
    }
    // 兼容旧数据：历史文档可能没有 file_hash，此时用文件名和类型兜底提示。
    return !item.file_hash && item.name === file.name && item.file_type === fileType;
  });
}

export function Knowledge() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [duplicateNotice, setDuplicateNotice] = useState<{ title: string; content: string } | null>(null);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      setDocuments(await listKnowledgeDocuments());
    } catch (error) {
      message.error(error instanceof Error ? error.message : TEXT.loadFailed);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const uploadProps: UploadProps = {
    accept: ".txt,.md",
    showUploadList: false,
    beforeUpload: async (file) => {
      setDuplicateNotice(null);
      let fileHash: string | undefined;
      try {
        fileHash = await calculateFileHash(file);
        const duplicate = findDuplicateDocument(documents, file, fileHash);
        if (duplicate) {
          const isProcessing = duplicate.status === TEXT.processing;
          setDuplicateNotice({
            title: isProcessing ? TEXT.duplicateProcessingTitle : TEXT.duplicateTitle,
            content: `文档「${duplicate.name}」与本次上传文件内容相同，${isProcessing ? "当前仍在处理中，请稍后再试。" : "无需重复上传。"}`
          });
          return Upload.LIST_IGNORE;
        }
      } catch {
        const duplicate = findDuplicateDocument(documents, file);
        if (duplicate) {
          setDuplicateNotice({
            title: duplicate.status === TEXT.processing ? TEXT.duplicateProcessingTitle : TEXT.duplicateTitle,
            content: `文档「${duplicate.name}」可能已经存在。当前历史数据缺少文件 hash，请先确认是否需要重复上传。`
          });
          return Upload.LIST_IGNORE;
        }
        // 浏览器侧 hash 计算失败时继续走后端校验，避免影响正常上传。
      }

      const tempId = -Date.now();
      const pendingDocument: KnowledgeDocument = {
        id: tempId,
        name: file.name,
        file_type: getFileType(file.name),
        file_hash: fileHash,
        status: TEXT.processing,
        error_message: null,
        chunk_count: 0,
        created_at: new Date().toISOString()
      };

      setDocuments((items) => [pendingDocument, ...items]);
      setUploading(true);
      try {
        const result = await uploadKnowledgeDocument(file);
        setDocuments((items) => items.map((item) => (item.id === tempId ? result : item)));
        if (result.status === TEXT.failed) {
          message.error(result.error_message || TEXT.uploadFailed);
        } else {
          message.success(TEXT.uploadSuccess);
        }
        await loadDocuments();
      } catch (error) {
        // 409 重复文档、鉴权失败、网络失败等请求级错误不会生成真实文档，移除本地临时行即可。
        setDocuments((items) => items.filter((item) => item.id !== tempId));
        const errorMessage = error instanceof Error ? error.message : TEXT.uploadFailed;
        if (errorMessage.includes("相同内容") || errorMessage.includes("正在处理中")) {
          setDuplicateNotice({
            title: errorMessage.includes("正在处理中") ? TEXT.duplicateProcessingTitle : TEXT.duplicateTitle,
            content: errorMessage
          });
        } else {
          message.error(errorMessage);
        }
        await loadDocuments();
      } finally {
        setUploading(false);
      }
      return false;
    }
  };

  const removeDocument = async (documentId: number) => {
    if (documentId < 0) {
      setDocuments((items) => items.filter((item) => item.id !== documentId));
      return;
    }

    try {
      await deleteKnowledgeDocument(documentId);
      message.success(TEXT.deleteSuccess);
      await loadDocuments();
    } catch (error) {
      message.error(error instanceof Error ? error.message : TEXT.deleteFailed);
    }
  };

  return (
    <div className="knowledge-page">
      <div className="knowledge-toolbar">
        <div>
          <div className="knowledge-title">{TEXT.title}</div>
          <div className="knowledge-hint">{TEXT.uploadHint}</div>
        </div>
        <Upload {...uploadProps}>
          <Button type="primary" loading={uploading}>
            {TEXT.upload}
          </Button>
        </Upload>
      </div>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={documents}
        locale={{ emptyText: <Empty description={TEXT.empty} /> }}
        pagination={false}
        columns={[
          { title: TEXT.name, dataIndex: "name" },
          { title: TEXT.type, dataIndex: "file_type", width: 90 },
          { title: TEXT.status, dataIndex: "status", width: 100, render: renderStatus },
          { title: "Chunks", dataIndex: "chunk_count", width: 100 },
          {
            title: TEXT.uploadTime,
            dataIndex: "created_at",
            width: 190,
            render: (value: string) => new Date(value).toLocaleString()
          },
          {
            title: TEXT.action,
            width: 100,
            render: (_, record) =>
              record.status === TEXT.processing ? null : (
                <Popconfirm
                  title={TEXT.deleteTitle}
                  description={TEXT.deleteDescription}
                  okText={TEXT.delete}
                  cancelText={TEXT.cancel}
                  onConfirm={() => removeDocument(record.id)}
                >
                  <Button danger size="small" type="text">
                    {TEXT.delete}
                  </Button>
                </Popconfirm>
              )
          }
        ]}
      />
      <Modal
        title={duplicateNotice?.title}
        open={duplicateNotice !== null}
        okText="知道了"
        cancelButtonProps={{ style: { display: "none" } }}
        onOk={() => setDuplicateNotice(null)}
        onCancel={() => setDuplicateNotice(null)}
      >
        <p>{duplicateNotice?.content}</p>
      </Modal>
    </div>
  );
}
