from .ProjectController import ProjectController
import os
from .BaseController import BaseController
from langchain_text_splitters import RecursiveCharacterTextSplitter
from models import ProcessingEnums
from helpers.markdown_book_parser import parse_markdown_book, page_at


class ProcessingController(BaseController):
    def __init__(self, project_id: int):
        super().__init__()
        self.project_id = project_id
        self.project_path = ProjectController().get_or_create_project_path(project_id=project_id)

    def get_file_ext(self, file_id: str):
        return os.path.splitext(file_id)[-1].lower()

    def get_file_content(self, file_id: str):
        if self.get_file_ext(file_id=file_id) != ProcessingEnums.MD.value:
            return None

        file_path = os.path.join(self.project_path, file_id)
        if not os.path.exists(file_path):
            return None

        with open(file_path, encoding="utf-8") as f:
            return f.read()

    def get_parents(self, file_id: str):
        file_content = self.get_file_content(file_id=file_id)
        if file_content is None:
            return None

        parse_result = parse_markdown_book(text=file_content)
        if parse_result is None:
            return None

        return parse_result.parents

    def get_children(self, parent, chunk_size: int, chunk_overlap: int,
                     min_chunk_size: int = 60):
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            add_start_index=True,
            separators=["\n\n", "\n", ". ", "، ", " ", ""],
        )

        parent_text, page_offsets = parent.build_text()
        documents = text_splitter.create_documents([parent_text])

        spans = []
        for document in documents:
            start = document.metadata["start_index"]
            end = start + len(document.page_content)
            if spans and len(document.page_content) < min_chunk_size:
                spans[-1] = (spans[-1][0], max(spans[-1][1], end))
            elif spans and spans[-1][1] - spans[-1][0] < min_chunk_size:
                spans[-1] = (spans[-1][0], end)
            else:
                spans.append((start, end))

        children = []
        for start, end in spans:
            end = end - 1
            children.append({
                "text": parent_text[start:end + 1],
                "metadata": {
                    "parent_title": parent.title,
                    "breadcrumb": parent.breadcrumb,
                    "page_start": page_at(page_offsets, start),
                    "page_end": page_at(page_offsets, end),
                },
            })

        return children

    def process_file(self, file_id: str, chunk_size: int = 350, chunk_overlap: int = 50):
        parents = self.get_parents(file_id=file_id)
        if not parents:
            return None

        return [
            {
                "text": parent.text,
                "metadata": {**parent.metadata, "file_id": file_id},
                "order": parent.order,
                "children": self.get_children(
                    parent=parent,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                ),
            }
            for parent in parents
        ]
