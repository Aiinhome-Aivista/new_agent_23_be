import uuid
from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base

class GenerationSession(Base):
    __tablename__ = "generation_sessions"
    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, index=True)
    tech_profile = Column(JSON)
    status = Column(String, default="INITIALIZED")
    created_at = Column(DateTime, default=datetime.utcnow)

    artifacts = relationship("Artifact", back_populates="session", cascade="all, delete-orphan")
    decompositions = relationship("RequirementDecomposition", back_populates="session", cascade="all, delete-orphan")
    services = relationship("ServiceContract", back_populates="session", cascade="all, delete-orphan")

class Artifact(Base):
    __tablename__ = "artifacts"
    artifact_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("generation_sessions.session_id"))
    filename = Column(String)
    file_type = Column(String)
    raw_text = Column(Text)
    parsed_json_metadata = Column(JSON)

    session = relationship("GenerationSession", back_populates="artifacts")

class RequirementDecomposition(Base):
    __tablename__ = "requirement_decompositions"
    req_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("generation_sessions.session_id"))
    rule_text = Column(Text)
    rule_type = Column(String)
    source_reference = Column(String)

    session = relationship("GenerationSession", back_populates="decompositions")

class ServiceContract(Base):
    __tablename__ = "service_contracts"
    service_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("generation_sessions.session_id"))
    name = Column(String)
    methods = Column(JSON)
    dependencies = Column(JSON)
    status = Column(String, default="PROPOSED")

    session = relationship("GenerationSession", back_populates="services")
    tests = relationship("UnitTest", back_populates="service", cascade="all, delete-orphan")

class UnitTest(Base):
    __tablename__ = "unit_tests"
    test_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(UUID(as_uuid=True), ForeignKey("service_contracts.service_id"))
    test_name = Column(String)
    code_content = Column(Text)
    target_rule_ids = Column(JSON)
    framework = Column(String)

    service = relationship("ServiceContract", back_populates="tests")

class CoverageMatrix(Base):
    __tablename__ = "coverage_matrices"
    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    req_id = Column(UUID(as_uuid=True), ForeignKey("requirement_decompositions.req_id"))
    test_id = Column(UUID(as_uuid=True), ForeignKey("unit_tests.test_id"), nullable=True)
    status = Column(String)
    reviewer_decision = Column(Text, nullable=True)
