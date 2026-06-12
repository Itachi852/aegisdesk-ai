import { Button, Empty, Popconfirm, Table, Upload, message } from "antd";
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
  cancel: "取消",
  empty: "暂无文档",
  name: "文档名称",
  type: "类型",
  status: "状态",
  uploadTime: "上传时间",
  action: "操作"
};

export function Knowledge() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

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
      setUploading(true);
      try {
        await uploadKnowledgeDocument(file);
        message.success(TEXT.uploadSuccess);
        await loadDocuments();
      } catch (error) {
        message.error(error instanceof Error ? error.message : TEXT.uploadFailed);
      } finally {
        setUploading(false);
      }
      return false;
    }
  };

  const removeDocument = async (documentId: number) => {
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
          { title: TEXT.status, dataIndex: "status", width: 100 },
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
            render: (_, record) => (
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
    </div>
  );
}
