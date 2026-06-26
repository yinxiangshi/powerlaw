export type UploadDocumentsState = {
  status: "idle" | "success" | "error";
  message: string;
  uploaded: number;
};

export const initialUploadDocumentsState: UploadDocumentsState = {
  status: "idle",
  message: "",
  uploaded: 0,
};
