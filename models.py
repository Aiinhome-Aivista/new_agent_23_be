import uuid
from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Text
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import relationship
from database import Base

UUID = Uuid

class GenerationSession(Base):
    __tablename__ = "generation_sessions"
    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), index=True, nullable=True)
    tech_profile = Column(JSON)
    status = Column(String(50), default="INITIALIZED")
    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), index=True)
    tech_profile = Column(JSON)
    status = Column(String(255), default="INITIALIZED")
    created_at = Column(DateTime, default=datetime.utcnow)

    artifacts = relationship("Artifact", back_populates="session", cascade="all, delete-orphan")
    decompositions = relationship("RequirementDecomposition", back_populates="session", cascade="all, delete-orphan")
    services = relationship("ServiceContract", back_populates="session", cascade="all, delete-orphan")

class Artifact(Base):
    __tablename__ = "artifacts"
    artifact_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("generation_sessions.session_id"))
    filename = Column(String(255))
    file_type = Column(String(50))
    artifact_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("generation_sessions.session_id"))
    filename = Column(String(255))
    file_type = Column(String(255))
    raw_text = Column(Text)
    parsed_json_metadata = Column(JSON)

    session = relationship("GenerationSession", back_populates="artifacts")

class RequirementDecomposition(Base):
    __tablename__ = "requirement_decompositions"
    req_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("generation_sessions.session_id"))
    rule_code = Column(String(50), nullable=True)
    rule_text = Column(Text)
    rule_type = Column(String(50))
    rule_type = Column(String(255))
    source_reference = Column(String(255))

    session = relationship("GenerationSession", back_populates="decompositions")

class ServiceContract(Base):
    __tablename__ = "service_contracts"
    service_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("generation_sessions.session_id"))
    name = Column(String(255))
    methods = Column(JSON)
    dependencies = Column(JSON)
    status = Column(String(50), default="PROPOSED")
    service_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("generation_sessions.session_id"))
    name = Column(String(255))
    methods = Column(JSON)
    dependencies = Column(JSON)
    status = Column(String(255), default="PROPOSED")

    session = relationship("GenerationSession", back_populates="services")
    tests = relationship("UnitTest", back_populates="service", cascade="all, delete-orphan")

class UnitTest(Base):
    __tablename__ = "unit_tests"
    test_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_id = Column(String(36), ForeignKey("service_contracts.service_id"))
    test_name = Column(String(255))
    code_content = Column(Text)
    target_rule_ids = Column(JSON)
    framework = Column(String(50))
    test_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(UUID(as_uuid=True), ForeignKey("service_contracts.service_id"))
    test_name = Column(String(255))
    code_content = Column(Text)
    target_rule_ids = Column(JSON)
    framework = Column(String(255))

    service = relationship("ServiceContract", back_populates="tests")

class CoverageMatrix(Base):
    __tablename__ = "coverage_matrices"
    audit_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), nullable=True)
    req_id = Column(String(36), ForeignKey("requirement_decompositions.req_id"))
    test_id = Column(String(36), ForeignKey("unit_tests.test_id"), nullable=True)
    rule_code = Column(String(50), nullable=True)
    rule_text = Column(Text, nullable=True)
    service_name = Column(String(255), nullable=True)
    test_name = Column(String(255), nullable=True)
    status = Column(String(50), default="COVERED")
    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    req_id = Column(UUID(as_uuid=True), ForeignKey("requirement_decompositions.req_id"))
    test_id = Column(UUID(as_uuid=True), ForeignKey("unit_tests.test_id"), nullable=True)
    status = Column(String(255))
    reviewer_decision = Column(Text, nullable=True)
