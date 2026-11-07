import {
  BadRequestException,
  Controller,
  Get,
  Inject,
  NotFoundException,
  Param,
  Query,
  StreamableFile,
  UseFilters,
} from '@nestjs/common';
import { createReadStream } from 'node:fs';
import type { GetSchoolModelPort } from '../../../application/ports/inbound/get-school-model.port.js';
import type { GetSchoolModelAssetPort } from '../../../application/ports/inbound/get-school-model-asset.port.js';
import type { ListSchoolModelsPort } from '../../../application/ports/inbound/list-school-models.port.js';
import {
  GET_SCHOOL_MODEL,
  GET_SCHOOL_MODEL_ASSET,
  LIST_SCHOOL_MODELS,
} from '../../nest/model-catalog.tokens.js';
import {
  ModelCatalogPresenter,
  type SchoolModelHttpResponse,
} from './model-catalog.presenter.js';
import { ModelCatalogProblemDetailsFilter } from './model-catalog-problem-details.filter.js';

const MODEL_ID_PATTERN = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;
const MAX_LIMIT = 24;
const MAX_SEARCH_LENGTH = 100;

function parseInteger(value: string | undefined, name: string, fallback: number, min: number, max: number): number {
  if (value === undefined || value === '') return fallback;
  if (!/^-?\d+$/.test(value)) throw new BadRequestException(`${name} must be an integer.`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < min || parsed > max) {
    throw new BadRequestException(`${name} must be between ${min} and ${max}.`);
  }
  return parsed;
}

@Controller('models')
@UseFilters(ModelCatalogProblemDetailsFilter)
export class ModelCatalogController {
  constructor(
    @Inject(LIST_SCHOOL_MODELS)
    private readonly listModels: ListSchoolModelsPort,
    @Inject(GET_SCHOOL_MODEL)
    private readonly getModel: GetSchoolModelPort,
    @Inject(GET_SCHOOL_MODEL_ASSET)
    private readonly getModelAsset: GetSchoolModelAssetPort,
  ) {}

  @Get()
  async list(
    @Query('search') search?: string,
    @Query('offset') offsetValue?: string,
    @Query('limit') limitValue?: string,
  ) {
    const offset = parseInteger(offsetValue, 'offset', 0, 0, Number.MAX_SAFE_INTEGER);
    const limit = parseInteger(limitValue, 'limit', 9, 1, MAX_LIMIT);
    const normalizedSearch = search?.trim();
    if (normalizedSearch && normalizedSearch.length > MAX_SEARCH_LENGTH) {
      throw new BadRequestException(`search must be at most ${MAX_SEARCH_LENGTH} characters.`);
    }
    const result = await this.listModels.execute({
      ...(normalizedSearch ? { search: normalizedSearch } : {}),
      offset,
      limit,
    });
    return ModelCatalogPresenter.toPage(result);
  }

  @Get(':id')
  async get(@Param('id') id: string): Promise<SchoolModelHttpResponse> {
    this.validateId(id);
    const model = await this.getModel.execute(id);
    if (!model) throw new NotFoundException('School model not found.');
    return ModelCatalogPresenter.toModel(model);
  }

  @Get(':id/asset')
  async asset(@Param('id') id: string): Promise<StreamableFile> {
    return this.streamAsset(id, 'asset');
  }

  @Get(':id/thumbnail')
  async thumbnail(@Param('id') id: string): Promise<StreamableFile> {
    return this.streamAsset(id, 'thumbnail');
  }

  private validateId(id: string): void {
    if (!MODEL_ID_PATTERN.test(id)) throw new BadRequestException('Invalid model id.');
  }

  private async streamAsset(id: string, variant: 'asset' | 'thumbnail'): Promise<StreamableFile> {
    this.validateId(id);
    const asset = await this.getModelAsset.execute(id, variant);
    if (!asset) throw new NotFoundException('School model asset not found.');
    return new StreamableFile(createReadStream(asset.path), {
      type: asset.contentType,
      disposition: 'inline',
    });
  }
}
