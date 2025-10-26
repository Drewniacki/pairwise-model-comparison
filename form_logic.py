import streamlit as st

class ChunkForm:
    NAME_OPTIONS = ["Eva", "Gosia", "Krzysiek", "Tomek", "Michał", "Damian"]
    CHUNK_SIZE_OPTIONS = ["right", "too small", "too big"]
    WELL_ASSIGNMENT_OPTIONS = [
        "correct well is assigned", 
        "the assigned well is not mentioned in the text", 
        "the well mentioned in the text is not assigned",
        "assigned well is not an actuall well name"]
    CHUNK_INFO_OPTIONS = [
        "processed correctly", 
        "missing information", 
        "hallucinated"]
    WELL_DIAGRAM_OPTIONS = ["Yes", "No"]

    def has_missing_fields():
        if "missing_fields" in st.session_state:
            return bool(len(st.session_state.missing_fields))
        return False
    
    def submitted():
        if "form_submitted" in st.session_state:
            return st.session_state.form_submitted
        return False

    def submitted_correctly():
        if ChunkForm.submitted():
            if not ChunkForm.has_missing_fields():
                return True
        return False

    def onclick():

        st.session_state.missing_fields = []
        if not st.session_state.name:
            st.session_state.missing_fields.append("Name")
        if not st.session_state.chunk_size:
            st.session_state.missing_fields.append("Chunk Size")
        if not st.session_state.well_assignment:
            st.session_state.missing_fields.append("Well Assignment")
        if not st.session_state.chunk_info:
            st.session_state.missing_fields.append("Chunk Information")
        if not st.session_state.well_diagram:
            st.session_state.missing_fields.append("Well Diagram")

        st.session_state.form_submitted = True

    def set_session(chunk):
        # form values
        if "form_submitted" not in st.session_state:
            st.session_state.form_submitted = False
        if "missing_fileds" not in st.session_state:
            st.session_state.missing_fileds = []
        
        # chunk info
        st.session_state.chunk_uuid = chunk['chunk_uuid']