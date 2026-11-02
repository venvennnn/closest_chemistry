const MAX_SIDE = 2048;
const MAX_BYTES = 3_500_000;

export async function prepareImageFile(file: File): Promise<File> {
  const bitmap = await decodeImage(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    throw new Error("Could not prepare this photograph for upload.");
  }
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  let quality = 0.86;
  let blob = await canvasToJpeg(canvas, quality);
  while (blob.size > MAX_BYTES && quality > 0.45) {
    quality -= 0.12;
    blob = await canvasToJpeg(canvas, quality);
  }
  if (blob.size > MAX_BYTES) {
    throw new Error("This photograph is still too large after compression. Try a screenshot or a smaller JPEG.");
  }
  const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
  return new File([blob], name, { type: "image/jpeg" });
}

async function decodeImage(file: File): Promise<ImageBitmap> {
  try {
    return await createImageBitmap(file);
  } catch {
    throw new Error(
      "This photo could not be read. iPhone HEIC often fails here — in Photos, share as JPEG, or take a screenshot.",
    );
  }
}

function canvasToJpeg(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) resolve(blob);
        else reject(new Error("Could not compress this photograph."));
      },
      "image/jpeg",
      quality,
    );
  });
}
