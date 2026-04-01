import { Pinecone } from '@pinecone-database/pinecone';
import { settings } from '../core/config';

let pc: Pinecone | null = null;
let index: any = null;

export const getPineconeIndex = async () => {
  if (index) return index;
  if (!settings.PINECONE_API_KEY) return null;

  try {
    if (!pc) {
      pc = new Pinecone({ apiKey: settings.PINECONE_API_KEY });
    }

    const indexes = await pc.listIndexes();
    const indexNames = indexes.indexes?.map(i => i.name) || [];

    if (!indexNames.includes(settings.PINECONE_INDEX_NAME)) {
      await pc.createIndex({
        name: settings.PINECONE_INDEX_NAME,
        dimension: 768, // Dimension for gemini-embedding-2-preview
        metric: "cosine",
        spec: {
          serverless: {
            cloud: "aws",
            region: "us-east-1"
          }
        }
      });
    }

    index = pc.index(settings.PINECONE_INDEX_NAME);
    return index;
  } catch (error) {
    console.error("Pinecone Initialization Error:", error);
    return null;
  }
};

export const upsertCandidateVector = async (candidateId: number, embedding: number[], metadata: any) => {
  const idx = await getPineconeIndex();
  if (!idx) return false;

  try {
    await idx.upsert([
      {
        id: candidateId.toString(),
        values: embedding,
        metadata: metadata
      }
    ]);
    return true;
  } catch (error) {
    console.error("Pinecone Upsert Error:", error);
    return false;
  }
};

export const queryCandidates = async (embedding: number[], topK: number = 10) => {
  const idx = await getPineconeIndex();
  if (!idx) return [];

  try {
    const results = await idx.query({
      vector: embedding,
      topK: topK,
      includeMetadata: true
    });
    return results.matches || [];
  } catch (error) {
    console.error("Pinecone Query Error:", error);
    return [];
  }
};
